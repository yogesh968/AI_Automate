"""The orchestrator: owns state, the mic loop, turns, confirmations, speech and reminders."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import time
import uuid
from typing import Any

from . import PLATFORM, __version__
from .brain.agent import Hooks, run_agent
from .brain.llm import LLM, MissingKey
from .config import Settings
from .context import ctx
from .memory.store import Store
from .secrets import key_status, set_key
from .tools.base import load_all
from .voice.mic import Mic, Recorder, is_hallucination, rms
from .voice.tts import TTS, SentenceSplitter
from .voice.wakeword import WakeWord

log = logging.getLogger(__name__)

YES = re.compile(r"\b(haan|haa|han|ha|hanji|haanji|yes|yeah|yep|ok|okay|sure|kar do|karo|kardo|theek hai|thik hai|"
                 r"chalo|go ahead|do it|confirm|bilkul|zaroor)\b|हाँ|हां|हा|कर दो|करो|ठीक है|बिल्कुल|ज़रूर|जरूर",
                 re.I)
# checked before YES ("nahi, mat karo" contains "karo"). No bare "na"/"ना": it's a common tag ("kar do na").
NO = re.compile(r"\b(nahi|nahin|nai|no|nope|mat|ruko|ruk|cancel|stop|don't|dont|rehne do)\b|नहीं|नही|मत करो|रुको|रहने दो",
                re.I)


class Speaker:
    """Turns streamed reply text into ordered audio messages for one reply."""

    def __init__(self, core: "Core", reply_id: str) -> None:
        self.core = core
        self.id = reply_id
        self.splitter = SentenceSplitter()
        self.queue: asyncio.Queue[str | None] = asyncio.Queue()
        self.seq = 0
        self.prev = ""
        self.enabled = bool(core.settings["speak_replies"])
        self.worker = asyncio.create_task(self._work())

    def feed(self, text: str) -> None:
        if self.enabled:
            for piece in self.splitter.feed(text):
                self.queue.put_nowait(piece)

    def say(self, text: str) -> None:
        """Speak a complete sentence right away (flushes what's buffered first)."""
        if self.enabled:
            for piece in self.splitter.flush() + [text]:
                self.queue.put_nowait(piece)

    async def drain(self) -> None:
        """Wait until everything queued so far has been synthesized and sent."""
        while self.enabled and (not self.queue.empty() or self._busy):
            await asyncio.sleep(0.05)

    _busy = False

    async def finish(self) -> None:
        if self.enabled:
            for piece in self.splitter.flush():
                self.queue.put_nowait(piece)
        self.queue.put_nowait(None)
        await self.worker
        await self.core.broadcast({"type": "audio_end", "id": self.id})

    def cancel(self) -> None:
        self.worker.cancel()

    async def _work(self) -> None:
        while True:
            item = await self.queue.get()
            if item is None:
                return
            self._busy = True
            try:
                audio, _provider = await self.core.tts.synth(item, self.prev)
                if audio:
                    await self.core.broadcast({
                        "type": "audio", "id": self.id, "seq": self.seq, "format": "mp3",
                        "data": base64.b64encode(audio).decode(), "text": item,
                    })
                    self.seq += 1
                    self.core.expect_audio = True
                    await self.core.set_state("speaking")
                self.prev = item
            finally:
                self._busy = False


class Core:
    def __init__(self) -> None:
        self.settings = Settings()
        self.store = Store()
        self.llm = LLM(self.settings)
        self.tts = TTS(self.settings)
        ctx.settings, ctx.store, ctx.llm = self.settings, self.store, self.llm
        ctx.notify = self.notify
        load_all()

        self.clients: set[Any] = set()
        self.state = "idle"
        self.turn_task: asyncio.Task | None = None
        self.pending: dict[str, asyncio.Future] = {}
        self.voice_confirm_id: str | None = None

        self.mic: Mic | None = None
        self.wake = WakeWord()
        self.mic_mode = "wake"          # wake | record | off
        self.mic_muted = False
        self.recorder: Recorder | None = None
        self.listen_purpose = "command"  # command | confirm
        self.noise_floor = 0.004
        self.cooldown_until = 0.0

        self.audio_playing = False
        self.audio_idle = asyncio.Event()
        self.audio_idle.set()
        self.expect_audio = False
        self._last_level_sent = 0.0

    # ------------------------------------------------------------------ plumbing

    async def broadcast(self, msg: dict[str, Any]) -> None:
        if not self.clients:
            return
        data = json.dumps(msg, ensure_ascii=False, default=str)
        for ws in list(self.clients):
            try:
                await ws.send(data)
            except Exception:
                self.clients.discard(ws)

    async def set_state(self, state: str) -> None:
        if state != self.state:
            self.state = state
            await self.broadcast({"type": "state", "state": state})

    async def notify(self, title: str, body: str, kind: str = "info") -> None:
        await self.broadcast({"type": "notify", "title": title, "body": body, "kind": kind})

    def hello(self) -> dict[str, Any]:
        return {"type": "hello", "version": __version__, "platform": PLATFORM, "keys": key_status(),
                "settings": self.settings.all(), "state": self.state}

    def _idle_state(self) -> str:
        return "sleeping" if self.mic_muted else "idle"

    # ------------------------------------------------------------------ messages from UI

    async def handle(self, msg: dict[str, Any]) -> None:
        kind = msg.get("type")
        if kind == "text":
            text = (msg.get("text") or "").strip()
            if text:
                await self.start_turn(text)
        elif kind == "listen":
            await self.begin_listening("command", push_to_talk=False)
        elif kind == "ptt_start":
            await self.begin_listening("command", push_to_talk=True)
        elif kind == "ptt_stop":
            if self.recorder and self.recorder.ptt:
                await self._finish_recording("done")
        elif kind == "confirm_response":
            self._resolve_confirm(msg.get("id", ""), bool(msg.get("approved")))
        elif kind == "stop":
            await self.stop()
        elif kind == "audio_state":
            self.audio_playing = bool(msg.get("playing"))
            if self.audio_playing:
                self.audio_idle.clear()
            else:
                self.audio_idle.set()
                self.cooldown_until = time.time() + 0.6
                if self.state == "speaking" and (self.turn_task is None or self.turn_task.done()):
                    await self.set_state(self._idle_state())
        elif kind == "mic_mute":
            self.mic_muted = bool(msg.get("muted"))
            if self.state in ("idle", "sleeping"):
                await self.set_state(self._idle_state())
        elif kind == "set_keys":
            for provider in ("groq", "elevenlabs"):
                if provider in msg and msg[provider] is not None:
                    set_key(provider, str(msg[provider]))
            self.tts.eleven_off_until = 0
            await self.broadcast({"type": "keys", **key_status()})
        elif kind == "update_settings":
            new = self.settings.update(msg.get("settings") or {})
            await self.broadcast({"type": "settings", "settings": new})
        elif kind == "get_audit":
            entries = self.store.recent_audit(int(msg.get("limit") or 100))
            await self.broadcast({"type": "audit", "entries": entries})
        elif kind == "get_history":
            await self.broadcast({"type": "history", "messages": self.store.recent_messages(int(msg.get("limit") or 50))})
        elif kind == "clear_history":
            self.store.clear_messages()
            await self.broadcast({"type": "history", "messages": []})
        else:
            log.debug("unknown message %s", kind)

    # ------------------------------------------------------------------ turns

    async def start_turn(self, text: str) -> None:
        await self._cancel_turn()
        self.turn_task = asyncio.create_task(self._turn(text))

    async def _cancel_turn(self) -> None:
        for fut in self.pending.values():
            if not fut.done():
                fut.set_result(False)
        if self.turn_task and not self.turn_task.done():
            self.turn_task.cancel()
            try:
                await self.turn_task
            except (asyncio.CancelledError, Exception):
                pass
        self.turn_task = None

    async def stop(self) -> None:
        """Kill switch."""
        await self._cancel_turn()
        self.recorder = None
        self.mic_mode = "wake"
        self.voice_confirm_id = None
        await self.set_state(self._idle_state())
        log.info("kill switch: everything stopped")

    def _hindi(self, deva: str, roman: str) -> str:
        return deva if self.settings["hindi_script"] == "devanagari" else roman

    async def _turn(self, text: str) -> None:
        reply_id = uuid.uuid4().hex[:12]
        speaker = Speaker(self, reply_id)
        self.expect_audio = False
        await self.set_state("thinking")

        async def on_text(chunk: str) -> None:
            await self.broadcast({"type": "assistant_delta", "id": reply_id, "text": chunk})
            speaker.feed(chunk)

        async def on_tool_start(call_id: str, name: str, args: dict, level: str) -> None:
            await self.broadcast({"type": "tool_start", "id": call_id, "name": name, "args": args, "level": level})

        async def on_tool_end(call_id: str, ok: bool, summary: str) -> None:
            await self.broadcast({"type": "tool_end", "id": call_id, "ok": ok, "summary": summary})

        async def confirm(call_id: str, name: str, args: dict, description: str) -> bool:
            return await self._confirm(call_id, name, args, description, speaker)

        reply = ""
        try:
            reply = await run_agent(text, Hooks(on_text, on_tool_start, on_tool_end, confirm))
        except asyncio.CancelledError:
            speaker.cancel()
            await self.broadcast({"type": "assistant_done", "id": reply_id, "text": "(stopped)"})
            raise
        except MissingKey as exc:
            reply = str(exc)
            await self.broadcast({"type": "assistant_delta", "id": reply_id, "text": reply})
            speaker.say(self._hindi("Groq की API key नहीं मिली, Settings में paste कर दो।",
                                    "Groq ki API key nahi mili, Settings mein paste kar do."))
            await self.notify("API key needed", reply, "warning")
        except Exception as exc:  # noqa: BLE001
            log.exception("turn failed")
            reply = self._hindi("माफ़ करना, कुछ गड़बड़ हो गई — ", "Sorry, kuch gadbad ho gayi — ") + _friendly(exc)
            await self.broadcast({"type": "assistant_delta", "id": reply_id, "text": reply})
            speaker.say(reply)
            await self.broadcast({"type": "error", "message": f"{type(exc).__name__}: {exc}"})

        await speaker.finish()
        await self.broadcast({"type": "assistant_done", "id": reply_id, "text": reply})
        if not self.expect_audio or not self.clients:
            await self.set_state(self._idle_state())
        elif not self.audio_playing:
            # audio already finished (or hasn't started yet); give the UI a moment, then go idle
            asyncio.create_task(self._idle_fallback())

    async def _idle_fallback(self) -> None:
        await asyncio.sleep(2)
        if self.state == "speaking" and not self.audio_playing and (self.turn_task is None or self.turn_task.done()):
            await self.set_state(self._idle_state())

    # ------------------------------------------------------------------ confirmations

    async def _confirm(self, call_id: str, name: str, args: dict, description: str, speaker: Speaker) -> bool:
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self.pending[call_id] = fut
        await self.broadcast({"type": "confirm_request", "id": call_id, "tool": name, "args": args,
                              "description": description})
        await self.notify("Approval needed", description, "warning")
        speaker.say(self._hindi("इसके लिए आपका OK चाहिए — हाँ या ना?", "Iske liye aapka OK chahiye — haan ya na?"))
        if self.settings["confirm_by_voice"] and self.mic:
            asyncio.create_task(self._listen_for_confirm(call_id, speaker))
        try:
            approved = await asyncio.wait_for(fut, timeout=120)
        except asyncio.TimeoutError:
            approved = False
        finally:
            self.pending.pop(call_id, None)
            if self.voice_confirm_id == call_id:
                self.voice_confirm_id = None
                if self.mic_mode == "record" and self.listen_purpose == "confirm":
                    self.recorder = None
                    self.mic_mode = "wake"
        await self.broadcast({"type": "confirm_resolved", "id": call_id, "approved": approved})
        await self.set_state("thinking")
        return approved

    def _resolve_confirm(self, call_id: str, approved: bool) -> None:
        fut = self.pending.get(call_id)
        if fut and not fut.done():
            fut.set_result(approved)

    async def _listen_for_confirm(self, call_id: str, speaker: Speaker) -> None:
        await speaker.drain()
        await asyncio.sleep(0.3)
        try:
            await asyncio.wait_for(self.audio_idle.wait(), timeout=20)
        except asyncio.TimeoutError:
            pass
        if call_id not in self.pending:
            return
        self.voice_confirm_id = call_id
        await self.begin_listening("confirm", push_to_talk=False)

    # ------------------------------------------------------------------ listening

    async def begin_listening(self, purpose: str, push_to_talk: bool) -> None:
        if not self.mic:
            await self.notify("Microphone", "No microphone available — type instead.", "error")
            return
        if purpose == "command" and self.voice_confirm_id:
            purpose = "confirm"
        self.listen_purpose = purpose
        self.recorder = Recorder(self.noise_floor, push_to_talk=push_to_talk)
        self.mic_mode = "record"
        self.wake.reset()
        await self.set_state("listening")

    async def _finish_recording(self, status: str) -> None:
        rec, purpose = self.recorder, self.listen_purpose
        self.recorder = None
        self.mic_mode = "wake"
        self.wake.reset()
        if rec is None:
            return
        if status == "nothing" or not rec.has_speech():
            if purpose == "command":
                await self.set_state(self._idle_state())
            else:
                await self.set_state("thinking")
            return
        await self.set_state("thinking")
        asyncio.create_task(self._transcribe(rec.wav(), purpose))

    async def _transcribe(self, wav: bytes, purpose: str) -> None:
        try:
            text = await self.llm.transcribe(wav)
        except MissingKey as exc:
            await self.notify("API key needed", str(exc), "warning")
            await self.set_state(self._idle_state())
            return
        except Exception as exc:  # noqa: BLE001
            log.exception("transcription failed")
            await self.notify("Speech-to-text failed", _friendly(exc), "error")
            await self.set_state(self._idle_state())
            return
        if is_hallucination(text):
            if purpose == "command":
                await self.set_state(self._idle_state())
            return
        await self.broadcast({"type": "transcript", "text": text, "final": True})
        if purpose == "confirm" and self.voice_confirm_id:
            call_id = self.voice_confirm_id
            if NO.search(text):
                self._resolve_confirm(call_id, False)
            elif YES.search(text):
                self._resolve_confirm(call_id, True)
            else:
                # not a yes/no — treat it as a new instruction
                self._resolve_confirm(call_id, False)
                await self.start_turn(text)
            return
        await self.start_turn(text)

    async def mic_loop(self) -> None:
        loop = asyncio.get_running_loop()
        self.mic = Mic(loop)
        if not self.mic.start():
            self.mic = None
            await self.notify("Microphone", "Couldn't open the microphone — voice is off, typing still works.", "error")
            return
        wake_ok = await asyncio.to_thread(self.wake.load) if self.settings["wake_word_enabled"] else False
        if self.settings["wake_word_enabled"] and not wake_ok:
            await self.notify("Wake word", "Wake word failed to load — use the hotkey or click the orb.", "warning")
        while True:
            frame = await self.mic.queue.get()
            level = rms(frame)
            if self.mic_mode == "wake":
                if not self.audio_playing and level < 0.05:
                    self.noise_floor = 0.97 * self.noise_floor + 0.03 * level
                if (self.mic_muted or self.audio_playing or time.time() < self.cooldown_until
                        or not self.settings["wake_word_enabled"] or not wake_ok):
                    continue
                score = self.wake.score(frame)
                if score >= float(self.settings["wake_word_threshold"]):
                    log.info("wake word (%.2f)", score)
                    if self.turn_task and not self.turn_task.done():
                        await self._cancel_turn()
                    await self.begin_listening("command", push_to_talk=False)
            elif self.mic_mode == "record" and self.recorder:
                now = time.time()
                if now - self._last_level_sent > 0.05:
                    self._last_level_sent = now
                    await self.broadcast({"type": "mic_level", "level": min(1.0, level * 12)})
                status = self.recorder.feed(frame)
                if status != "continue":
                    await self._finish_recording(status)

    # ------------------------------------------------------------------ reminders

    async def reminder_loop(self) -> None:
        while True:
            await asyncio.sleep(10)
            try:
                for rem in self.store.due_reminders(time.time()):
                    self.store.complete_reminder(rem)
                    await self.notify("Reminder", rem["text"], "reminder")
                    await self.speak(self._hindi("Reminder: ", "Reminder: ") + rem["text"])
            except Exception:
                log.exception("reminder loop")

    async def speak(self, text: str) -> None:
        """Speak something outside a normal turn (reminders)."""
        speaker = Speaker(self, uuid.uuid4().hex[:12])
        await self.broadcast({"type": "assistant_done", "id": speaker.id, "text": text})
        speaker.say(text)
        await speaker.finish()

    # ------------------------------------------------------------------ lifecycle

    async def run_background(self) -> None:
        await asyncio.gather(self.mic_loop(), self.reminder_loop())


def _friendly(exc: Exception) -> str:
    text = str(exc)
    low = text.lower()
    if "401" in text or "invalid api key" in low or "authentication" in low:
        return "API key galat lag rahi hai, Settings mein check karo."
    if "429" in text or "rate limit" in low:
        return "Groq ki rate limit hit ho gayi, thodi der mein try karo."
    if "connect" in low or "timeout" in low or "network" in low:
        return "internet connection mein problem hai."
    return text[:160]
