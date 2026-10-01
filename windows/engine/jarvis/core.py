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
from .brain.learn import learn_from_turn
from .brain.llm import LLM, MissingKey
from .config import Settings
from .context import ctx
from .memory.store import Store
from .monitor import AlertRules, Telemetry, greeting
from .paths import data_file
from .secrets import get_key, key_status, set_key
from .tools.base import REGISTRY, load_all
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
        ctx.broadcast = self.broadcast
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

        # follow-up conversation: after a spoken reply to a voice command, listen again without the wake word
        self.followup_wanted = False
        # HUD + telemetry + proactive alerts
        self.telemetry = Telemetry()
        self.alerts = AlertRules()
        self.hud_open = False
        self.last_snapshot: dict[str, Any] | None = None
        self._weather: dict[str, Any] | None = None
        self._weather_t = 0.0
        self.greeted = False
        self.background_tasks: set[asyncio.Task] = set()

    def _spawn(self, coro) -> asyncio.Task:
        """Fire-and-forget task that is kept alive and whose errors are logged."""
        task = asyncio.create_task(coro)
        self.background_tasks.add(task)

        def done(t: asyncio.Task) -> None:
            self.background_tasks.discard(t)
            if not t.cancelled() and t.exception():
                log.error("background task failed", exc_info=t.exception())

        task.add_done_callback(done)
        return task

    # ------------------------------------------------------------------ persona lines

    @property
    def classic(self) -> bool:
        return (self.settings["persona"] or "classic") == "classic"

    @property
    def sir(self) -> str:
        return (self.settings["address_as"] or "").strip() or self.settings["user_name"] or "sir"

    def line(self, key: str) -> str:
        """Short fixed phrases, in the voice of the selected persona."""
        sir = self.sir
        if self.classic:
            return {
                "confirm": f"I'll need your go-ahead for that, {sir}. Yes or no?",
                "no_key": f"I can't reach my language systems, {sir}. The Groq API key is missing — it goes in Settings.",
                "sorry": f"Apologies, {sir}, something went wrong — ",
                "reminder": f"{sir.capitalize()}, a reminder: ",
            }[key]
        return {
            "confirm": self._hindi("इसके लिए आपका OK चाहिए — हाँ या ना?", "Iske liye aapka OK chahiye — haan ya na?"),
            "no_key": self._hindi("Groq की API key नहीं मिली, Settings में paste कर दो।",
                                  "Groq ki API key nahi mili, Settings mein paste kar do."),
            "sorry": self._hindi("माफ़ करना, कुछ गड़बड़ हो गई — ", "Sorry, kuch gadbad ho gayi — "),
            "reminder": "Reminder: ",
        }[key]

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
                await self.start_turn(text, voice=False)
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
                turn_done = self.turn_task is None or self.turn_task.done()
                if self.state == "speaking" and turn_done:
                    await self.set_state(self._idle_state())
                if turn_done and self.followup_wanted:
                    self._spawn(self._follow_up())
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
        elif kind == "hud_state":
            self.hud_open = bool(msg.get("open"))
            if self.hud_open:
                self._spawn(self._push_hud(force=True))
        else:
            log.debug("unknown message %s", kind)

    # ------------------------------------------------------------------ turns

    async def start_turn(self, text: str, voice: bool = True) -> None:
        await self._cancel_turn()
        self.followup_wanted = False
        self.turn_task = asyncio.create_task(self._turn(text, voice))

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
        self.followup_wanted = False
        await self.set_state(self._idle_state())
        log.info("kill switch: everything stopped")

    async def interrupt(self) -> None:
        """Barge-in: the user said "Hey Jarvis" while Jarvis was talking — shut up and listen."""
        await self._cancel_turn()
        self.followup_wanted = False
        await self.broadcast({"type": "interrupt"})
        # don't wait for the UI's audio_state round-trip before listening
        self.audio_playing = False
        self.audio_idle.set()
        await self.begin_listening("command", push_to_talk=False)

    async def _follow_up(self) -> None:
        """Keep the conversation going: listen for a few seconds after a spoken reply."""
        self.followup_wanted = False
        if not (self.settings["follow_up"] and self.mic and not self.mic_muted):
            return
        await asyncio.sleep(0.35)  # let the speaker's tail die away so we don't hear ourselves
        if self.audio_playing or self.mic_mode != "wake" or (self.turn_task and not self.turn_task.done()):
            return
        await self.begin_listening("followup", push_to_talk=False)

    def _hindi(self, deva: str, roman: str) -> str:
        return deva if self.settings["hindi_script"] == "devanagari" else roman

    async def _turn(self, text: str, voice: bool = True) -> None:
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
        ok = False
        try:
            reply = await run_agent(text, Hooks(on_text, on_tool_start, on_tool_end, confirm))
            ok = True
        except asyncio.CancelledError:
            speaker.cancel()
            await self.broadcast({"type": "assistant_done", "id": reply_id, "text": "(stopped)"})
            raise
        except MissingKey as exc:
            reply = str(exc)
            await self.broadcast({"type": "assistant_delta", "id": reply_id, "text": reply})
            speaker.say(self.line("no_key"))
            await self.notify("API key needed", reply, "warning")
        except Exception as exc:  # noqa: BLE001
            log.exception("turn failed")
            reply = self.line("sorry") + _friendly(exc)
            await self.broadcast({"type": "assistant_delta", "id": reply_id, "text": reply})
            speaker.say(reply)
            await self.broadcast({"type": "error", "message": f"{type(exc).__name__}: {exc}"})

        if ok and reply:
            self._spawn(self._learn(text, reply))
        await speaker.finish()
        await self.broadcast({"type": "assistant_done", "id": reply_id, "text": reply})
        # Only a successful spoken exchange keeps the conversation open.
        self.followup_wanted = ok and voice
        if not self.expect_audio or not self.clients:
            await self.set_state(self._idle_state())
            if self.followup_wanted:
                self._spawn(self._follow_up())
        elif not self.audio_playing:
            # audio already finished (or hasn't started yet); give the UI a moment, then go idle
            self._spawn(self._idle_fallback())

    async def _idle_fallback(self) -> None:
        await asyncio.sleep(2)
        if self.state == "speaking" and not self.audio_playing and (self.turn_task is None or self.turn_task.done()):
            await self.set_state(self._idle_state())
            if self.followup_wanted:
                await self._follow_up()

    async def _learn(self, user_text: str, reply: str) -> None:
        saved = await learn_from_turn(user_text, reply)
        for fact in saved:
            await self.notify("Noted", fact, "memory")

    # ------------------------------------------------------------------ confirmations

    async def _confirm(self, call_id: str, name: str, args: dict, description: str, speaker: Speaker) -> bool:
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self.pending[call_id] = fut
        await self.broadcast({"type": "confirm_request", "id": call_id, "tool": name, "args": args,
                              "description": description})
        await self.notify("Approval needed", description, "warning")
        speaker.say(self.line("confirm"))
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
        # a follow-up only waits a few seconds for the user to start talking
        self.recorder = Recorder(self.noise_floor, push_to_talk=push_to_talk,
                                 start_timeout=5.0 if purpose == "followup" else 6.0)
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
            if purpose in ("command", "followup"):
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
            if purpose in ("command", "followup"):
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
                if self.mic_muted or not self.settings["wake_word_enabled"] or not wake_ok:
                    continue
                threshold = float(self.settings["wake_word_threshold"])
                if self.audio_playing:
                    # Barge-in: while Jarvis talks, a much stricter threshold so its own voice can't trigger it.
                    if not self.settings["barge_in"]:
                        continue
                    score = self.wake.score(frame)
                    if score >= min(0.95, threshold + 0.25):
                        log.info("barge-in wake word (%.2f)", score)
                        await self.interrupt()
                    continue
                if time.time() < self.cooldown_until:
                    continue
                score = self.wake.score(frame)
                if score >= threshold:
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
                    await self.speak(self.line("reminder") + rem["text"])
            except Exception:
                log.exception("reminder loop")

    async def speak(self, text: str) -> None:
        """Speak something outside a normal turn (reminders)."""
        speaker = Speaker(self, uuid.uuid4().hex[:12])
        await self.broadcast({"type": "assistant_done", "id": speaker.id, "text": text})
        speaker.say(text)
        await speaker.finish()

    # ------------------------------------------------------------------ boot greeting

    async def on_connect(self) -> None:
        """Called by the server after a UI connects."""
        if self.greeted:
            return
        self.greeted = True
        if not self.settings["startup_greeting"]:
            return
        # The engine restarts after a crash; don't greet again if we did a minute ago.
        stamp = data_file("last_greeting")
        try:
            if stamp.exists() and time.time() - float(stamp.read_text() or 0) < 20 * 60:
                return
        except (OSError, ValueError):
            pass
        try:
            stamp.write_text(str(time.time()))
        except OSError:
            pass
        self._spawn(self._greet())

    async def _greet(self) -> None:
        await asyncio.sleep(1.2)  # let the UI finish booting its audio
        # battery only — a full snapshot here would skew the telemetry loop's CPU sampling window
        snap = self.last_snapshot or {"battery": await asyncio.to_thread(self.telemetry.battery)}
        text = greeting(self.settings["persona"] or "classic", (self.settings["address_as"] or "").strip(),
                        self.settings["user_name"], self.settings["hindi_script"], snap)
        if not get_key("groq"):
            text += (" One thing first: I'll need a Groq API key in Settings before I can think for you."
                     if self.classic else " Bas ek kaam — Settings mein Groq API key daal do.")
        await self.speak(text)

    # ------------------------------------------------------------------ telemetry, HUD, proactive alerts

    def _busy(self) -> bool:
        return (self.state in ("listening", "thinking") or self.audio_playing
                or bool(self.turn_task and not self.turn_task.done()))

    async def _weather_now(self) -> dict[str, Any] | None:
        if self._weather and time.time() - self._weather_t < 30 * 60:
            return self._weather
        try:
            from .tools.web import weather

            data = await asyncio.to_thread(weather, self.settings["home_city"] or "")
            self._weather, self._weather_t = data, time.time()
        except Exception as exc:  # noqa: BLE001 — offline / API down: HUD just hides the card
            log.debug("weather unavailable: %s", exc)
            self._weather_t = time.time() - 25 * 60  # retry in ~5 min
        return self._weather

    async def _push_hud(self, force: bool = False) -> None:
        """Weather, reminders and memory stats for the HUD (stats themselves stream separately)."""
        if not (self.hud_open or force):
            return
        reminders = [{"text": r["text"], "due": r["due"], "repeat": r["repeat"]}
                     for r in self.store.pending_reminders()[:6]]
        await self.broadcast({
            "type": "hud_info",
            "weather": await self._weather_now(),
            "reminders": reminders,
            "memories": len(self.store.all_facts(limit=10000)),
            "tools": len(REGISTRY),
        })
        if self.last_snapshot:
            await self.broadcast({"type": "system_stats", "stats": self.last_snapshot})

    async def telemetry_loop(self) -> None:
        """Streams stats while the HUD is open (every 1.5 s) and checks alert rules (every ~15 s)."""
        last_alert_check = time.time() - 5  # first check ~10 s after boot, once the greeting is done
        last_info = time.time()
        first = True
        while True:
            await asyncio.sleep(1.5 if self.hud_open else 5)
            now = time.time()
            due_alerts = now - last_alert_check >= 15
            if not (self.hud_open or due_alerts):
                continue
            try:
                if due_alerts:
                    await asyncio.to_thread(self.telemetry.check_online)
                snap = await asyncio.to_thread(self.telemetry.snapshot, self.hud_open or due_alerts)
                self.last_snapshot = snap
                if self.hud_open:
                    await self.broadcast({"type": "system_stats", "stats": snap})
                    if now - last_info > 60:
                        last_info = now
                        await self._push_hud()
                if due_alerts:
                    last_alert_check = now
                    alerts = self.alerts.feed(snap, now)
                    if first:
                        # the first reading only primes the rules (the greeting covers boot state) — except a
                        # nearly full disk, which nothing else would mention for hours
                        first = False
                        alerts = [a for a in alerts if a.key == "disk"]
                    if self.settings["proactive_alerts"]:
                        for alert in alerts:
                            await self._announce(alert)
            except Exception:
                log.exception("telemetry loop")

    async def _announce(self, alert) -> None:
        await self.notify(alert.title, alert.en, alert.kind)
        if self._busy():
            return  # never talk over the user or over an answer; the toast is enough
        text = f"{self.sir.capitalize()}, {alert.en[0].lower()}{alert.en[1:]}" if self.classic else alert.hi
        await self.speak(text)

    # ------------------------------------------------------------------ lifecycle

    async def run_background(self) -> None:
        await asyncio.gather(self.mic_loop(), self.reminder_loop(), self.telemetry_loop())


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
