"""Groq client: streaming chat with tool calls, vision, and Whisper speech-to-text."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from ..config import Settings
from ..secrets import get_key

log = logging.getLogger(__name__)


class MissingKey(RuntimeError):
    pass


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

    def client(self):
        key = get_key("groq")
        if not key:
            raise MissingKey("Groq API key is not set. Open Settings and paste it.")
        if key != self._key or self._client is None:
            from groq import AsyncGroq

            self._client = AsyncGroq(api_key=key, max_retries=2, timeout=60)
            self._key = key
        return self._client

    def _extra(self, model: str) -> dict[str, Any]:
        if model.startswith("openai/gpt-oss"):
            return {"reasoning_effort": "low", "include_reasoning": False}
        return {}

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        on_text: Callable[[str], Awaitable[None]],
    ) -> tuple[str, list[dict[str, Any]]]:
        """Stream a completion. Calls on_text for each text chunk. Returns (text, tool_calls)."""
        import groq

        models = [self.settings["llm_model"]]
        if self.settings["fast_model"] and self.settings["fast_model"] not in models:
            models.append(self.settings["fast_model"])
        last_exc: Exception | None = None
        for model in models:
            try:
                return await self._stream(model, messages, tools, on_text)
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
            except (groq.RateLimitError, groq.InternalServerError, groq.APIConnectionError) as exc:
                log.warning("model %s failed (%s), trying fallback", model, type(exc).__name__)
                last_exc = exc
                continue
        raise last_exc or RuntimeError("LLM failed")

    async def _stream(self, model, messages, tools, on_text):
        kwargs: dict[str, Any] = dict(model=model, messages=messages, stream=True, temperature=0.6,
                                      max_completion_tokens=2048)
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
        kwargs: dict[str, Any] = dict(model=model, messages=messages, temperature=0.3, max_completion_tokens=2048)
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
                                                           max_completion_tokens=512)
        return resp.choices[0].message.content or ""

    async def vision(self, image_b64_jpeg: str, prompt: str) -> str:
        resp = await self.client().chat.completions.create(
            model=self.settings["vision_model"],
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
