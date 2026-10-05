"""Tests for v0.2.2 speed work: instant commands, parallel tools, parallel speech, faster first sentence, trimmed audio."""

import asyncio
import os
import tempfile
import time

os.environ.setdefault("JARVIS_DATA_DIR", tempfile.mkdtemp(prefix="jarvis-test-"))

import numpy as np  # noqa: E402

from jarvis.brain import agent, quick  # noqa: E402
from jarvis.config import Settings  # noqa: E402
from jarvis.context import ctx  # noqa: E402
from jarvis.memory.store import Store  # noqa: E402
from jarvis.tools.base import REGISTRY, load_all  # noqa: E402
from jarvis.voice.mic import FRAME, RATE, Recorder  # noqa: E402
from jarvis.voice.tts import SentenceSplitter  # noqa: E402

load_all()


def m(text):
    q = quick.match(text)
    return (q.tool, q.args) if q else None


# ------------------------------------------------------------------ instant commands

def test_open_and_close_apps():
    assert m("chrome kholo") == ("open_app", {"name": "chrome"})
    assert m("Hey Jarvis, open Spotify.") == ("open_app", {"name": "Spotify"})
    assert m("vs code open karo") == ("open_app", {"name": "vs code"})
    assert m("zara whatsapp khol do na") == ("open_app", {"name": "whatsapp"})
    assert m("close safari") == ("close_app", {"name": "safari"})
    assert m("spotify band karo") == ("close_app", {"name": "spotify"})


def test_volume_media_time():
    assert m("volume 30") == ("set_volume", {"level": 30})
    assert m("volume 40 kar do") == ("set_volume", {"level": 40})
    assert m("volume badhao") == ("change_volume", {"delta": 10})
    assert m("awaaz kam karo") == ("change_volume", {"delta": -10})
    assert m("mute") == ("mute", {"muted": True})
    assert m("pause") == ("media_control", {"action": "play_pause"})
    assert m("agla gaana") == ("media_control", {"action": "next"})
    assert m("time kya hai?") == ("get_datetime", {})
    assert m("What's the time") == ("get_datetime", {})
    assert m("battery kitni hai") == ("battery_status", {})
    assert m("hud dikhao") == ("show_hud", {})


def test_anything_more_goes_to_the_llm():
    for text in ["youtube kholo", "open downloads folder", "chrome kholo aur youtube pe arijit chalao",
                 "close this window", "open google.com", "volume 300", "what's the weather",
                 "kal subah 7 baje gym ka reminder", "who is the prime minister of india",
                 "open the file I was working on yesterday in vs code"]:
        assert quick.match(text) is None, text


def test_failed_tool_falls_back():
    assert quick.failed("couldn't find an app called 'xyz'. Maybe it's not installed?")
    assert quick.failed("'Spotify' isn't running")
    assert not quick.failed("opened Google Chrome")


def test_replies_follow_language_and_script():
    s = Settings()
    s.update({"persona": "classic", "address_as": "sir", "hindi_script": "devanagari"})
    q = quick.match("chrome kholo")
    assert "खोल" in q.reply("opened Google Chrome", quick.Voice(s, q.hindi))
    q = quick.match("open chrome")
    assert q.reply("opened Google Chrome", quick.Voice(s, q.hindi)) == "Opening Google Chrome, sir."
    q = quick.match("battery status")
    assert q.reply("42% charging", quick.Voice(s, q.hindi)).startswith("Battery at 42 percent, charging")


class _Hooks:
    def __init__(self):
        self.text = ""

    async def on_text(self, t):
        self.text += t

    async def on_tool_start(self, *a):
        pass

    async def on_tool_end(self, *a):
        pass

    async def confirm(self, *a):
        return True


def _setup_ctx(llm):
    ctx.settings = Settings()
    ctx.settings.update({"persona": "classic", "address_as": "sir", "dry_run": False})
    ctx.store = Store()
    ctx.llm = llm


def test_instant_command_skips_the_llm(monkeypatch):
    class NoLLM:
        async def chat(self, *a, **k):
            raise AssertionError("LLM should not be called")

    _setup_ctx(NoLLM())
    tool = REGISTRY["set_volume"]
    monkeypatch.setattr(tool, "func", lambda level: f"volume set to {level}")
    h = _Hooks()
    hooks = agent.Hooks(h.on_text, h.on_tool_start, h.on_tool_end, h.confirm)
    reply = asyncio.run(agent.run_agent("volume 25", hooks))
    assert reply == "Volume at 25." and h.text == reply


def test_instant_command_falls_back_to_llm_when_tool_fails(monkeypatch):
    calls = []

    class FakeLLM:
        async def chat(self, messages, tools, on_text):
            calls.append(messages[-1]["content"])
            await on_text("Couldn't find it, sir.")
            return "Couldn't find it, sir.", []

    _setup_ctx(FakeLLM())
    monkeypatch.setattr(REGISTRY["open_app"], "func", lambda name: f"couldn't find an app called '{name}'.")
    h = _Hooks()
    reply = asyncio.run(agent.run_agent("open blorbo", agent.Hooks(h.on_text, h.on_tool_start, h.on_tool_end,
                                                                     h.confirm)))
    assert calls == ["open blorbo"] and reply == "Couldn't find it, sir."


def test_harmless_tool_calls_run_in_parallel(monkeypatch):
    _setup_ctx(None)
    monkeypatch.setattr(REGISTRY["get_datetime"], "func", lambda: (time.sleep(0.3), "now")[1])
    monkeypatch.setattr(REGISTRY["battery_status"], "func", lambda: (time.sleep(0.3), "50%")[1])
    h = _Hooks()
    hooks = agent.Hooks(h.on_text, h.on_tool_start, h.on_tool_end, h.confirm)
    calls = [{"id": "a", "name": "get_datetime", "arguments": "{}"},
             {"id": "b", "name": "battery_status", "arguments": "{}"}]
    started = time.monotonic()
    out = asyncio.run(agent._run_calls(calls, hooks))
    assert out == ["now", "50%"]
    assert time.monotonic() - started < 0.5


# ------------------------------------------------------------------ speech

def test_first_piece_can_end_at_a_comma():
    sp = SentenceSplitter()
    assert sp.feed("Battery at eighteen percent, sir, and about forty") == ["Battery at eighteen percent,"]
    # later pieces still wait for a full sentence
    assert sp.feed(" minutes left, so") == []


def test_speaker_synthesizes_in_parallel_but_sends_in_order():
    from jarvis.core import Speaker

    sent = []

    class FakeTTS:
        async def synth(self, text, prev=""):
            await asyncio.sleep(0.3 if text.startswith("One") else 0.05)
            return text.encode(), "fake"

    class FakeCore:
        settings = {"speak_replies": True}
        tts = FakeTTS()
        expect_audio = False

        async def broadcast(self, msg):
            if msg["type"] == "audio":
                sent.append(msg["text"])

        async def set_state(self, s):
            pass

    async def go():
        sp = Speaker(FakeCore(), "r1")
        sp.say("One moment, sir.")
        sp.say("Two.")
        sp.say("Three.")
        started = time.monotonic()
        await sp.finish()
        return time.monotonic() - started

    took = asyncio.run(go())
    assert sent == ["One moment, sir.", "Two.", "Three."]
    assert took < 0.5  # sequential would be 0.4 s+


# ------------------------------------------------------------------ recording

def test_recording_is_trimmed_to_the_speech():
    rec = Recorder(0.004)
    quiet = np.zeros(FRAME, dtype=np.int16)
    loud = (np.sin(np.arange(FRAME) / 3) * 8000).astype(np.int16)
    for _ in range(20):
        rec.feed(quiet)  # 1.6 s of silence before speaking
    for _ in range(10):
        rec.feed(loud)
    status = "continue"
    while status == "continue":
        status = rec.feed(quiet)
    assert status == "done"
    seconds = (len(rec.wav()) - 44) / 2 / RATE
    assert seconds < 1.6  # 0.8 s speech + padding, not 3 s
