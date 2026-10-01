"""Microphone capture (16 kHz mono int16, 80 ms frames) and end-of-speech detection."""

from __future__ import annotations

import asyncio
import io
import logging
import wave

import numpy as np

log = logging.getLogger(__name__)

RATE = 16000
FRAME = 1280  # 80 ms — what openWakeWord expects
FRAME_SEC = FRAME / RATE


def rms(frame: np.ndarray) -> float:
    return float(np.sqrt(np.mean((frame.astype(np.float32) / 32768.0) ** 2)))


class Mic:
    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.queue: asyncio.Queue[np.ndarray] = asyncio.Queue(maxsize=100)
        self.stream = None
        self.error = ""

    def _put(self, frame: np.ndarray) -> None:
        if self.queue.full():
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        self.queue.put_nowait(frame)

    def _callback(self, indata, frames, time_info, status) -> None:  # runs on the audio thread
        self.loop.call_soon_threadsafe(self._put, indata[:, 0].copy())

    def start(self) -> bool:
        try:
            import sounddevice as sd

            self.stream = sd.InputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=FRAME,
                                         callback=self._callback)
            self.stream.start()
            log.info("microphone started: %s", sd.query_devices(kind="input")["name"])
            return True
        except Exception as exc:  # noqa: BLE001
            self.error = f"{type(exc).__name__}: {exc}"
            log.error("microphone unavailable: %s", self.error)
            return False

    def stop(self) -> None:
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None


class Recorder:
    """Collects frames for one utterance and decides when the user stopped talking."""

    def __init__(self, noise_floor: float, push_to_talk: bool = False, start_timeout: float = 6.0) -> None:
        self.frames: list[np.ndarray] = []
        self.start_timeout = start_timeout
        self.threshold = max(noise_floor * 3.0, 0.012)
        self.ptt = push_to_talk
        self.started = False
        self.loud_run = 0
        self.silence = 0
        self.total = 0

    def feed(self, frame: np.ndarray) -> str:
        """Returns 'continue', 'done' or 'nothing' (no speech heard)."""
        self.frames.append(frame)
        self.total += 1
        level = rms(frame)
        if self.ptt:
            return "done" if self.total * FRAME_SEC > 60 else "continue"
        if level > self.threshold:
            self.loud_run += 1
            self.silence = 0
            if self.loud_run >= 2:
                self.started = True
        else:
            self.loud_run = 0
            if self.started:
                self.silence += 1
        seconds = self.total * FRAME_SEC
        if not self.started and seconds > self.start_timeout:
            return "nothing"
        if self.started and self.silence * FRAME_SEC >= 0.9:
            return "done"
        if seconds > 25:
            return "done"
        return "continue"

    def has_speech(self) -> bool:
        return self.started or (self.ptt and self.total * FRAME_SEC > 0.4)

    def wav(self) -> bytes:
        audio = np.concatenate(self.frames) if self.frames else np.zeros(FRAME, dtype=np.int16)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(audio.tobytes())
        return buf.getvalue()


# Whisper sometimes "hears" these in silence/noise.
HALLUCINATIONS = {
    "", "thank you.", "thank you", "thanks for watching!", "thanks for watching.", "you", ".", "bye.",
    "subtitles by the amara.org community", "please subscribe.", "धन्यवाद", "धन्यवाद।",
}


def is_hallucination(text: str) -> bool:
    return text.strip().lower() in HALLUCINATIONS
