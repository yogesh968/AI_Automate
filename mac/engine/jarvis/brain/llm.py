"""Groq client: streaming chat with tool calls, vision, and Whisper speech-to-text."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, Awaitable, Callable

from ..config import Settings
from ..secrets import get_key

log = logging.getLogger(__name__)


class MissingKey(RuntimeError):
    pass


# Every Groq model has its own tokens-per-minute budget, so when one is throttled we move straight
# on to the next instead of letting the SDK sleep 10–30 s on a retry.
CHAT_MODELS = ("openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b")
MAX_WAIT = 10.0  # longest we'll wait when every model is throttled


def _retry_after(exc: Exception) -> float:
    resp = getattr(exc, "response", None)
    try:
        value = float(resp.headers.get("retry-after"))  # type: ignore[union-attr]
    except (AttributeError, TypeError, ValueError):
        m = re.search(r"try again in ([\d.]+)(ms|s)", str(exc))
        value = (float(m.group(1)) / (1000 if m.group(2) == "ms" else 1)) if m else 10.0
    return max(1.0, value)


class _ThinkFilter:
    """Removes <think>…</think> blocks some reasoning models put in their text stream."""

    def __init__(self) -> None:
        self.inside = False
        self.buf = ""

    def feed(self, text: str) -> str:
        self.buf += text
        out = ""
        while self.buf:
            if self.inside:
                end = self.buf.find("</think>")
                if end < 0:
                    self.buf = self.buf[-8:]
                    return out
                self.buf = self.buf[end + 8:]
                self.inside = False
            else:
                start = self.buf.find("<think>")
                if start < 0:
                    # keep a possible partial "<think" at the end
                    keep = next((i for i in range(1, 7) if self.buf.endswith("<think>"[:i])), 0)
                    out += self.buf[: len(self.buf) - keep]
                    self.buf = self.buf[len(self.buf) - keep:]
                    return out
                out += self.buf[:start]
                self.buf = self.buf[start + 7:]
                self.inside = True
        return out


class LLM:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = None
        self._key = ""
        self._cooldown: dict[str, float] = {}  # model -> monotonic time it may be used again
        self._warmed = 0.0

    def client(self):
        key = get_key("groq")
        if not key:
            raise MissingKey("Groq API key is not set. Open Settings and paste it.")
        if key != self._key or self._client is None:
            import httpx
            from groq import AsyncGroq

            # Long keep-alive: reusing one TLS connection saves ~0.2-0.5 s on every request.
            http = httpx.AsyncClient(timeout=30, limits=httpx.Limits(max_keepalive_connections=8,
                                                                     keepalive_expiry=300))
            self._client = AsyncGroq(api_key=key, max_retries=0, timeout=30, http_client=http)
            self._key = key
        return self._client

    async def warm(self) -> None:
        """Open the connection to Groq ahead of time (called when the user starts talking)."""
        if time.monotonic() - self._warmed < 45:
            return
        self._warmed = time.monotonic()
        try:
            await self.client().models.list()
        except Exception as exc:  # noqa: BLE001 — just a warm-up
            log.debug("groq warm-up failed: %s", exc)

    def _extra(self, model: str) -> dict[str, Any]:
        if model.startswith("openai/gpt-oss"):
            return {"reasoning_effort": "low", "include_reasoning": False}
        if model.startswith("qwen/"):
            return {"reasoning_effort": "none"}
        return {}

    def _models(self) -> list[str]:
        models: list[str] = []
        for m in (self.settings["llm_model"], *CHAT_MODELS, self.settings["fast_model"]):
            if m and m not in models:
                models.append(m)
        return models

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        on_text: Callable[[str], Awaitable[None]],
    ) -> tuple[str, list[dict[str, Any]]]:
        """Stream a completion. Calls on_text for each text chunk. Returns (text, tool_calls)."""
        import groq

        last_exc: Exception | None = None
        for _attempt in range(3):
            ready = [m for m in self._models() if self._cooldown.get(m, 0) <= time.monotonic()]
            if not ready:
                wait = min(self._cooldown.values()) - time.monotonic()
                if wait > MAX_WAIT:
                    break
                await asyncio.sleep(max(0.0, wait))
                ready = [m for m in self._models() if self._cooldown.get(m, 0) <= time.monotonic()]
            for model in ready:
                try:
                    started = time.monotonic()
                    result = await self._stream(model, messages, tools, on_text)
                    log.info("%s answered in %.2fs (%d tools, %d tool calls)", model, time.monotonic() - started,
                             len(tools or []), len(result[1]))
                    return result
                except groq.RateLimitError as exc:
                    self._cooldown[model] = time.monotonic() + _retry_after(exc)
                    log.warning("%s is rate-limited, switching model", model)
                    last_exc = exc
                except groq.NotFoundError as exc:
                    self._cooldown[model] = time.monotonic() + 3600  # model retired
                    log.warning("%s is not available: %s", model, exc)
                    last_exc = exc
                except groq.BadRequestError as exc:
                    # tool_use_failed: the model produced a malformed tool call — retry without streaming
                    if "tool_use_failed" in str(exc) or "failed_generation" in str(exc):
                        log.warning("tool_use_failed on %s, retrying non-streaming", model)
                        try:
                            return await self._once(model, messages, tools, on_text)
                        except Exception as exc2:  # noqa: BLE001
                            last_exc = exc2
                            continue
                    raise
                except (groq.InternalServerError, groq.APIConnectionError, groq.APITimeoutError) as exc:
                    log.warning("model %s failed (%s), trying fallback", model, type(exc).__name__)
                    last_exc = exc
                except groq.APIStatusError as exc:
                    if exc.status_code != 413:  # 413: too big for this model's per-minute budget — try the next
                        raise
                    log.warning("request too large for %s, switching model", model)
                    last_exc = exc
            if not any(until > time.monotonic() for until in self._cooldown.values()):
                break  # nothing is just throttled, so waiting won't help
        raise last_exc or RuntimeError("LLM failed")

    async def _stream(self, model, messages, tools, on_text):
        kwargs: dict[str, Any] = dict(model=model, messages=messages, stream=True, temperature=0.6,
                                      max_completion_tokens=1024)
        if tools:
            kwargs.update(tools=tools, tool_choice="auto", parallel_tool_calls=True)
        extra = self._extra(model)
        if extra:
            kwargs["extra_body"] = extra
        stream = await self.client().chat.completions.create(**kwargs)
        text = ""
        calls: dict[int, dict[str, Any]] = {}
        think = _ThinkFilter()
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                clean = think.feed(delta.content)
                if clean:
                    text += clean
                    await on_text(clean)
            for tc in delta.tool_calls or []:
                slot = calls.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                if tc.id:
                    slot["id"] = tc.id
                if tc.function and tc.function.name:
                    slot["name"] += tc.function.name
                if tc.function and tc.function.arguments:
                    slot["arguments"] += tc.function.arguments
        return text, [calls[i] for i in sorted(calls)]

    async def _once(self, model, messages, tools, on_text):
        kwargs: dict[str, Any] = dict(model=model, messages=messages, temperature=0.3, max_completion_tokens=1024)
        if tools:
            kwargs.update(tools=tools, tool_choice="auto")
        extra = self._extra(model)
        if extra:
            kwargs["extra_body"] = extra
        resp = await self.client().chat.completions.create(**kwargs)
        msg = resp.choices[0].message
        text = _ThinkFilter().feed(msg.content or "")
        if text:
            await on_text(text)
        calls = [{"id": tc.id, "name": tc.function.name, "arguments": tc.function.arguments or "{}"}
                 for tc in (msg.tool_calls or [])]
        return text, calls

    async def complete(self, prompt: str, system: str = "", model: str | None = None) -> str:
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        model = model or self.settings["fast_model"]
        resp = await self.client().chat.completions.create(model=model, messages=messages, temperature=0.2,
                                                           max_completion_tokens=512,
                                                           extra_body=self._extra(model) or None)
        return resp.choices[0].message.content or ""

    async def vision(self, image_b64_jpeg: str, prompt: str) -> str:
        model = self.settings["vision_model"]
        resp = await self.client().chat.completions.create(
            model=model,
            extra_body=self._extra(model) or None,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64_jpeg}"}},
            ]}],
            temperature=0.2,
            max_completion_tokens=1024,
        )
        return resp.choices[0].message.content or ""

    async def transcribe(self, wav_bytes: bytes) -> str:
        resp = await self.client().audio.transcriptions.create(
            file=("speech.wav", wav_bytes),
            model=self.settings["stt_model"],
            prompt="Hinglish conversation with Jarvis, mixing Hindi and English. हाँ, ठीक है, open karo, please.",
            response_format="json",
            temperature=0.0,
        )
        return (getattr(resp, "text", "") or "").strip()
