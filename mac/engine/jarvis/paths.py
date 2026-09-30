"""Where JARVIS keeps its data (settings, memory db, logs, browser profile)."""

import os
from pathlib import Path


def data_dir() -> Path:
    env = os.environ.get("JARVIS_DATA_DIR")
    if env:
        base = Path(env)
    else:
        base = Path.home() / "Library" / "Application Support" / "Jarvis"
    base.mkdir(parents=True, exist_ok=True)
    return base


def data_file(name: str) -> Path:
    return data_dir() / name


def logs_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path
