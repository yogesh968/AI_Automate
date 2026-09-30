"""API keys in the OS keychain (Windows Credential Manager). Env vars override."""

import logging
import os

log = logging.getLogger(__name__)

SERVICE = "jarvis"
NAMES = {"groq": "groq_api_key", "elevenlabs": "elevenlabs_api_key"}
ENV = {"groq": "GROQ_API_KEY", "elevenlabs": "ELEVENLABS_API_KEY"}


def _keyring():
    try:
        import keyring

        return keyring
    except Exception:
        log.warning("keyring unavailable; only env vars will work for API keys")
        return None


def get_key(provider: str) -> str:
    env_value = os.environ.get(ENV[provider], "").strip()
    if env_value:
        return env_value
    kr = _keyring()
    if not kr:
        return ""
    try:
        return (kr.get_password(SERVICE, NAMES[provider]) or "").strip()
    except Exception:
        log.exception("could not read %s key from keychain", provider)
        return ""


def set_key(provider: str, value: str) -> None:
    kr = _keyring()
    if not kr:
        raise RuntimeError("OS keychain is not available")
    value = (value or "").strip()
    if value:
        kr.set_password(SERVICE, NAMES[provider], value)
    else:
        try:
            kr.delete_password(SERVICE, NAMES[provider])
        except Exception:
            pass


def key_status() -> dict[str, bool]:
    return {provider: bool(get_key(provider)) for provider in NAMES}
