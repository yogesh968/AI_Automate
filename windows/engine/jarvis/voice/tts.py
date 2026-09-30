"""Text-to-speech: ElevenLabs (natural, multilingual) with free Microsoft Edge voices as fallback."""

from __future__ import annotations

import logging
import re
import time

import httpx

from ..config import DEFAULT_ELEVENLABS_VOICE, Settings
from ..secrets import get_key

log = logging.getLogger(__name__)

_EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF️‍]+")
_URL = re.compile(r"https?://\S+|www\.\S+")


def clean_for_speech(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = _URL.sub(" link ", text)
    text = re.sub(r"[*_#`>|~]+", "", text)
    text = re.sub(r"^\s*[-•]\s+", "", text, flags=re.M)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.M)
    text = _EMOJI.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


class SentenceSplitter:
    """Cuts streamed text into speakable pieces. The first piece is short so speech starts fast."""

    BOUNDARY = re.compile(r"[.!?।]+[\"'”’)]*\s+|\n+")

    def __init__(self) -> None:
        self.buf = ""
        self.emitted = 0

    def feed(self, text: str) -> list[str]:
        self.buf += text
        out = []
        while True:
            min_len = 8 if self.emitted == 0 else 60
            cut = None
            for m in self.BOUNDARY.finditer(self.buf):
                if m.end() >= min_len:
                    cut = m.end()
                    break
            if cut is None:
                break
            piece, self.buf = self.buf[:cut].strip(), self.buf[cut:]
            if piece:
                out.append(piece)
                self.emitted += 1
        return out

    def flush(self) -> list[str]:
        piece, self.buf = self.buf.strip(), ""
        return [piece] if piece else []


class TTS:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.http = httpx.AsyncClient(timeout=30)
        self.eleven_off_until = 0.0
        self.last_error = ""

    async def synth(self, text: str, previous_text: str = "") -> tuple[bytes | None, str]:
        """Returns (mp3 bytes, provider used)."""
        text = clean_for_speech(text)
        if not text:
            return None, ""
        if self.settings["tts_provider"] == "elevenlabs" and get_key("elevenlabs") and time.time() > self.eleven_off_until:
            try:
                return await self._eleven(text, previous_text), "elevenlabs"
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"ElevenLabs: {exc}"
                log.warning("ElevenLabs failed, using Edge voice: %s", exc)
                self.eleven_off_until = time.time() + 300
        try:
            return await self._edge(text), "edge"
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"Edge TTS: {exc}"
            log.error("Edge TTS failed: %s", exc)
            return None, ""

    async def _eleven(self, text: str, previous_text: str) -> bytes:
        voice = self.settings["elevenlabs_voice_id"] or DEFAULT_ELEVENLABS_VOICE
        body = {
            "text": text,
            "model_id": self.settings["elevenlabs_model"] or "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.42, "similarity_boost": 0.8, "style": 0.3, "use_speaker_boost": True},
        }
        if previous_text:
            body["previous_text"] = previous_text[-300:]
        resp = await self.http.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
            params={"output_format": "mp3_44100_128"},
            headers={"xi-api-key": get_key("elevenlabs"), "accept": "audio/mpeg"},
            json=body,
        )
        if resp.status_code == 400 and "previous_text" in body:
            body.pop("previous_text")
            resp = await self.http.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
                params={"output_format": "mp3_44100_128"},
                headers={"xi-api-key": get_key("elevenlabs"), "accept": "audio/mpeg"},
                json=body,
            )
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        return resp.content

    async def _edge(self, text: str) -> bytes:
        import edge_tts

        voice = self.settings["edge_voice"] or "hi-IN-MadhurNeural"
        comm = edge_tts.Communicate(text, voice, rate="+4%")
        audio = bytearray()
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                audio.extend(chunk["data"])
        if not audio:
            raise RuntimeError("no audio returned")
        return bytes(audio)
