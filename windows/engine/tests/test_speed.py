"""Tests for the speed work: small per-request tool sets, model rotation on rate limits, settings migration."""

import asyncio
import json
import os
import tempfile

os.environ.setdefault("JARVIS_DATA_DIR", tempfile.mkdtemp(prefix="jarvis-test-"))

import groq  # noqa: E402
import httpx  # noqa: E402

from jarvis.brain import toolset  # noqa: E402
from jarvis.brain.llm import LLM  # noqa: E402
from jarvis.config import Settings  # noqa: E402
from jarvis.paths import data_file  # noqa: E402
from jarvis.tools.base import REGISTRY, load_all  # noqa: E402

load_all()


def names(groups):
    return {s["function"]["name"] for s in toolset.schemas(groups)}


def test_every_core_tool_exists():
    assert toolset.CORE_TOOLS <= set(REGISTRY)


def test_plain_command_sends_only_core_tools():
    groups = toolset.pick_groups("chrome kholo")
    assert groups == {toolset.CORE}
    sent = names(groups)
    assert "open_app" in sent and "load_tools" in sent
    assert "delete_path" not in sent
    assert len(json.dumps(toolset.schemas(groups))) // 4 < 2500  # vs ~7k tokens for all tools


def test_keywords_pull_in_groups():
    assert "files" in toolset.pick_groups("Downloads folder mein kitni files hain?")
    assert "reminders" in toolset.pick_groups("5 minute baad yaad dilana")
    assert "system" in toolset.pick_groups("brightness 70 kar do")
    assert "google_services" in toolset.pick_groups("check my email")


def test_all_groups_loaded_drops_loader():
    every = {toolset.CORE, *toolset.GROUPS}
    sent = names(every)
    assert "load_tools" not in sent
    assert sent == set(REGISTRY)


def test_recent_groups_carry_over_one_turn():
    toolset.remember_used({"core", "files"})
    assert "files" in toolset.pick_groups("haan karo")
    toolset.remember_used(set())
    assert "files" not in toolset.pick_groups("haan karo")


def _rate_limited(model):
    req = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    resp = httpx.Response(429, request=req, headers={"retry-after": "30"})
    return groq.RateLimitError(f"Rate limit reached for model `{model}`", response=resp, body=None)


def test_rate_limit_switches_model_without_waiting():
    llm = LLM(Settings())
    tried = []
    throttled = {llm._models()[0]}

    async def fake_stream(model, messages, tools, on_text):
        tried.append(model)
        if model in throttled:
            throttled.discard(model)  # only the first request is throttled
            raise _rate_limited(model)
        return "ok", []

    llm._stream = fake_stream

    async def noop(_):
        pass

    text, _ = asyncio.run(llm.chat([{"role": "user", "content": "hi"}], None, noop))
    assert text == "ok"
    assert tried[0] != tried[1]
    # the throttled model is skipped on the next request
    tried.clear()
    asyncio.run(llm.chat([{"role": "user", "content": "hi"}], None, noop))
    assert tried == [llm._models()[1]]


def test_retired_models_are_migrated():
    path = data_file("settings.json")
    path.write_text(json.dumps({
        "fast_model": "llama-3.1-8b-instant",
        "vision_model": "meta-llama/llama-4-scout-17b-16e-instruct",
        "llm_model": "openai/gpt-oss-120b",
        "elevenlabs_model": "eleven_multilingual_v2",
        "user_name": "Yogesh",
    }), encoding="utf-8")
    s = Settings()
    assert s["fast_model"] == "openai/gpt-oss-20b"
    assert s["vision_model"] == "qwen/qwen3.8-27b"
    assert s["llm_model"] == "openai/gpt-oss-120b"
    assert s["elevenlabs_model"] == "eleven_flash_v2_5"
    assert s["user_name"] == "Yogesh"
    # a deliberate choice made after the migration is kept
    s.update({"elevenlabs_model": "eleven_multilingual_v2"})
    assert Settings()["elevenlabs_model"] == "eleven_multilingual_v2"
