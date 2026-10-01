"""User settings stored as JSON in the data dir. See PROTOCOL.md for the fields."""

import json
import logging
import threading
from typing import Any

from .paths import data_file

log = logging.getLogger(__name__)

DEFAULTS: dict[str, Any] = {
    "user_name": "",
    "assistant_name": "Jarvis",
    "llm_model": "openai/gpt-oss-120b",
    "fast_model": "llama-3.1-8b-instant",
    "vision_model": "meta-llama/llama-4-scout-17b-16e-instruct",
    "stt_model": "whisper-large-v3-turbo",
    "tts_provider": "elevenlabs",
    "elevenlabs_voice_id": "",
    "elevenlabs_model": "eleven_multilingual_v2",
    "edge_voice": "hi-IN-MadhurNeural",
    "speak_replies": True,
    "hindi_script": "devanagari",
    "wake_word_enabled": True,
    "wake_word_threshold": 0.5,
    "dry_run": False,
    "allowed_write_dirs": [],
    "confirm_by_voice": True,
    "start_with_system": True,
    # --- "real JARVIS" behaviour ---
    "persona": "classic",          # classic (movie JARVIS, calls you "sir") | desi (casual Indian friend)
    "address_as": "sir",           # how the classic persona addresses the user
    "follow_up": True,             # keep listening briefly after a spoken reply (no wake word needed)
    "barge_in": True,              # "Hey Jarvis" while Jarvis is talking interrupts it
    "startup_greeting": True,      # "Good evening, sir. All systems online." when the app starts
    "proactive_alerts": True,      # speak up about low battery, CPU overload, internet down…
    "auto_memory": True,           # quietly learn lasting facts about the user from conversations
    "sound_effects": True,         # HUD chimes when listening starts/ends
    "home_city": "",               # weather on the HUD; empty = detect from IP
}

# Premade ElevenLabs voice used until the user picks one (ideally an Indian voice
# from the ElevenLabs Voice Library).
DEFAULT_ELEVENLABS_VOICE = "JBFqnCBsd6RMkjVDRZzb"


class Settings:
    def __init__(self) -> None:
        self._path = data_file("settings.json")
        self._lock = threading.Lock()
        self._data: dict[str, Any] = dict(DEFAULTS)
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            self._save()
            return
        try:
            stored = json.loads(self._path.read_text(encoding="utf-8"))
            for key, value in stored.items():
                if key in DEFAULTS:
                    self._data[key] = value
        except Exception:
            log.exception("settings.json is broken, using defaults")

    def _save(self) -> None:
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._path)

    def get(self, key: str) -> Any:
        return self._data.get(key, DEFAULTS.get(key))

    def __getitem__(self, key: str) -> Any:
        return self.get(key)

    def all(self) -> dict[str, Any]:
        return dict(self._data)

    def update(self, changes: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            for key, value in changes.items():
                if key not in DEFAULTS:
                    continue
                default = DEFAULTS[key]
                if isinstance(default, bool):
                    value = bool(value)
                elif isinstance(default, float):
                    value = float(value)
                elif isinstance(default, list):
                    value = [str(v) for v in (value or []) if str(v).strip()]
                elif isinstance(default, str):
                    value = str(value or "")
                self._data[key] = value
            self._save()
        return self.all()
