"""Tests for the "real JARVIS" layer: proactive alert rules, boot greeting, auto-memory filters, persona prompt."""

import datetime as dt
import os
import tempfile

os.environ.setdefault("JARVIS_DATA_DIR", tempfile.mkdtemp(prefix="jarvis-test-"))

from jarvis.brain.learn import is_duplicate, parse_facts, worth_checking  # noqa: E402
from jarvis.brain.prompts import system_prompt  # noqa: E402
from jarvis.config import Settings  # noqa: E402
from jarvis.monitor import AlertRules, Telemetry, greeting, part_of_day  # noqa: E402


def snap(**kw):
    base = {"cpu": 10, "ram": 40, "battery": None, "online": True, "top": [{"name": "chrome.exe"}]}
    base.update(kw)
    return base


def keys(alerts):
    return [a.key for a in alerts]


def test_battery_warns_once_per_threshold():
    r = AlertRules()
    bat = lambda p, plugged=False: snap(battery={"percent": p, "plugged": plugged, "minutes_left": 30})  # noqa: E731
    assert keys(r.feed(bat(50), 0)) == []
    assert keys(r.feed(bat(19), 10)) == ["battery_low"]
    assert keys(r.feed(bat(18), 20)) == []            # no repeat at the same threshold
    assert keys(r.feed(bat(9), 30)) == ["battery_low"]
    assert keys(r.feed(bat(4), 40)) == ["battery_low"]
    assert keys(r.feed(bat(3), 50)) == []
    r.feed(bat(30, plugged=True), 60)                  # charger resets the warnings
    assert keys(r.feed(bat(19), 70)) == ["battery_low"]


def test_battery_drop_straight_to_critical_warns_once():
    r = AlertRules()
    out = r.feed(snap(battery={"percent": 4, "plugged": False, "minutes_left": None}), 0)
    assert keys(out) == ["battery_low"]
    assert keys(r.feed(snap(battery={"percent": 4, "plugged": False, "minutes_left": None}), 10)) == []


def test_battery_full_once():
    r = AlertRules()
    full = snap(battery={"percent": 100, "plugged": True, "minutes_left": None})
    assert keys(r.feed(full, 0)) == ["battery_full"]
    assert keys(r.feed(full, 10)) == []


def test_cpu_needs_sustained_load_and_cools_down():
    r = AlertRules(cpu_high_secs=60, cooldown=600)
    assert keys(r.feed(snap(cpu=99), 0)) == []
    assert keys(r.feed(snap(cpu=99), 30)) == []
    out = r.feed(snap(cpu=99), 61)
    assert keys(out) == ["cpu"] and "chrome.exe" in out[0].en
    assert keys(r.feed(snap(cpu=99), 200)) == []      # cooldown
    assert keys(r.feed(snap(cpu=10), 300)) == []      # spike ended
    assert keys(r.feed(snap(cpu=99), 700)) == []      # new spike must be sustained again
    assert keys(r.feed(snap(cpu=99), 770)) == ["cpu"]


def test_short_cpu_spike_is_ignored():
    r = AlertRules(cpu_high_secs=60)
    r.feed(snap(cpu=99), 0)
    r.feed(snap(cpu=20), 30)
    assert keys(r.feed(snap(cpu=99), 70)) == []


def test_internet_drop_needs_two_failures_and_announces_recovery():
    r = AlertRules()
    assert keys(r.feed(snap(online=True), 0)) == []
    assert keys(r.feed(snap(online=False), 15)) == []          # one blip is ignored
    assert keys(r.feed(snap(online=True), 30)) == []           # …and no "back online" for a blip
    r.feed(snap(online=False), 45)
    assert keys(r.feed(snap(online=False), 60)) == ["net_down"]
    assert keys(r.feed(snap(online=False), 75)) == []
    assert keys(r.feed(snap(online=True), 90)) == ["net_up"]


def test_disk_full_alert_is_rare():
    r = AlertRules()
    assert keys(r.feed(snap(disk=90), 0)) == []
    out = r.feed(snap(disk=98.6, disk_free_gb=3), 10)
    assert keys(out) == ["disk"] and "3 gigabytes" in out[0].en
    assert keys(r.feed(snap(disk=98.6), 3600)) == []
    assert keys(r.feed(snap(disk=98.6), 6 * 3600 + 20)) == ["disk"]


def test_offline_at_boot_is_not_announced():
    r = AlertRules()
    r.feed(snap(online=False), 0)
    assert keys(r.feed(snap(online=False), 15)) == []


def test_part_of_day():
    assert [part_of_day(h) for h in (6, 13, 19, 23, 2)] == ["morning", "afternoon", "evening", "night", "night"]


def test_greeting_classic_and_desi():
    t = dt.datetime(2026, 10, 1, 19, 5)
    g = greeting("classic", "sir", "Yogesh", "devanagari", None, t)
    assert g.startswith("Good evening, sir.") and "7:05 PM" in g and "online" in g
    low = {"battery": {"percent": 12, "plugged": False, "minutes_left": 20}}
    assert "12 percent" in greeting("classic", "sir", "", "roman", low, t)
    assert "Yogesh" in greeting("desi", "", "Yogesh", "devanagari", None, t)
    assert "Working late" in greeting("classic", "", "", "roman", None, dt.datetime(2026, 10, 1, 1, 30))


def test_telemetry_snapshot_shape():
    s = Telemetry().snapshot()
    for k in ("cpu", "ram", "disk", "net_up_kbps", "net_down_kbps", "uptime_s", "processes", "top"):
        assert k in s
    assert 0 <= s["ram"] <= 100


def test_auto_memory_filters():
    assert not worth_checking("open chrome")
    assert not worth_checking("volume 30 kar do")
    assert worth_checking("my sister Priya's birthday is on 12 March, remind me every year")
    assert parse_facts('Sure: ["User\'s sister is Priya.", 5, "x"]') == ["User's sister is Priya."]
    assert parse_facts("nothing here") == []
    assert parse_facts("[]") == []
    assert is_duplicate("User's sister is named Priya.", ["User's sister is Priya."])
    assert not is_duplicate("User works as a web developer.", ["User's sister is Priya."])


def test_persona_prompt():
    s = Settings()
    s.update({"persona": "classic", "address_as": "sir", "user_name": "Yogesh"})
    p = system_prompt(s, [])
    assert "Just A Rather Very Intelligent System" in p and '"sir"' in p
    s.update({"persona": "desi"})
    p = system_prompt(s, [])
    assert "Indian friend" in p and "Just A Rather" not in p
    s.update({"persona": "classic"})


# ---------------------------------------------------------------- conversation flow (core, no real mic)

def _core():
    import asyncio  # noqa: F401
    from jarvis.core import Core

    core = Core()
    calls = []

    async def fake_listen(purpose, push_to_talk):
        calls.append(purpose)

    core.begin_listening = fake_listen
    core.mic = object()  # pretend a microphone exists
    sent = []

    async def fake_broadcast(msg):
        sent.append(msg)

    core.broadcast = fake_broadcast
    return core, calls, sent


def test_follow_up_listens_after_spoken_reply_ends():
    import asyncio

    async def go():
        core, calls, _ = _core()
        core.followup_wanted = True
        await core.handle({"type": "audio_state", "playing": True})
        await core.handle({"type": "audio_state", "playing": False})
        await asyncio.sleep(0.5)
        return calls, core.followup_wanted

    calls, wanted = asyncio.run(go())
    assert calls == ["followup"] and wanted is False


def test_no_follow_up_when_disabled_or_muted():
    import asyncio

    async def go(patch):
        core, calls, _ = _core()
        patch(core)
        core.followup_wanted = True
        await core.handle({"type": "audio_state", "playing": False})
        await asyncio.sleep(0.5)
        return calls

    assert asyncio.run(go(lambda c: c.settings.update({"follow_up": False}))) == []
    assert asyncio.run(go(lambda c: setattr(c, "mic_muted", True))) == []
    # restore for other tests
    from jarvis.config import Settings
    Settings().update({"follow_up": True})


def test_typed_message_does_not_start_follow_up():
    import asyncio

    async def go():
        core, calls, _ = _core()

        async def fake_agent(text, hooks):
            await hooks.on_text("Done, sir.")
            return "Done, sir."

        import jarvis.core as core_mod
        real_agent, core_mod.run_agent = core_mod.run_agent, fake_agent
        core.settings.update({"speak_replies": False, "auto_memory": False})
        await core.handle({"type": "text", "text": "open notepad"})
        await core.turn_task
        await asyncio.sleep(0.5)
        typed = list(calls)
        await core.start_turn("open notepad", voice=True)
        await core.turn_task
        await asyncio.sleep(0.5)
        core.settings.update({"speak_replies": True, "auto_memory": True})
        core_mod.run_agent = real_agent
        return typed, calls

    typed, after_voice = asyncio.run(go())
    assert typed == []
    assert after_voice == ["followup"]


def test_barge_in_interrupt_stops_and_listens():
    import asyncio

    async def go():
        core, calls, sent = _core()
        core.audio_playing = True
        core.followup_wanted = True
        await core.interrupt()
        return calls, sent, core.audio_playing, core.followup_wanted

    calls, sent, playing, wanted = asyncio.run(go())
    assert calls == ["command"]
    assert {"type": "interrupt"} in sent
    assert playing is False and wanted is False
