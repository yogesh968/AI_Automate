"""'Hey Jarvis' wake word, fully offline (openWakeWord)."""

from __future__ import annotations

import logging

import numpy as np

log = logging.getLogger(__name__)


class WakeWord:
    def __init__(self) -> None:
        self.model = None
        self.error = ""

    def load(self) -> bool:
        try:
            import openwakeword
            from openwakeword.model import Model

            try:
                openwakeword.utils.download_models(model_names=["hey_jarvis"])
            except Exception as exc:  # already downloaded / offline
                log.debug("wake word model download skipped: %s", exc)
            self.model = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
            log.info("wake word ready (hey jarvis)")
            return True
        except Exception as exc:  # noqa: BLE001
            self.error = f"{type(exc).__name__}: {exc}"
            log.error("wake word unavailable: %s", self.error)
            return False

    def score(self, frame: np.ndarray) -> float:
        if not self.model:
            return 0.0
        scores = self.model.predict(frame)
        return max(scores.values()) if scores else 0.0

    def reset(self) -> None:
        if self.model:
            try:
                self.model.reset()
            except Exception:
                pass
