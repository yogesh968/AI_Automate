"""Entry point: python -m jarvis --port 8765 --token secret"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import secrets
import sys
import threading
import time
from logging.handlers import RotatingFileHandler

from .paths import logs_dir


def _setup_logging() -> None:
    level = os.environ.get("JARVIS_LOG_LEVEL", "INFO").upper()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(level)
    err = logging.StreamHandler(sys.stderr)
    err.setFormatter(fmt)
    root.addHandler(err)
    # (the app separately captures our stdout/stderr into engine.log)
    file = RotatingFileHandler(logs_dir() / "engine-core.log", maxBytes=2 * 2**20, backupCount=3, encoding="utf-8")
    file.setFormatter(fmt)
    root.addHandler(file)
    for noisy in ("httpx", "httpcore", "websockets", "comtypes", "PIL", "urllib3", "primp"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _watch_parents() -> None:
    """Exit if the app that started us dies, so we never linger holding the microphone."""
    try:
        import psutil
    except ImportError:
        return
    me = psutil.Process()
    chain = []
    p = me.parent()
    while p is not None:
        chain.append(p.pid)
        try:
            if not p.name().lower().startswith("python"):
                break  # the first non-python ancestor is the real parent (Electron / shell)
            p = p.parent()
        except psutil.Error:
            break

    def loop() -> None:
        while True:
            time.sleep(3)
            if any(not psutil.pid_exists(pid) for pid in chain):
                logging.getLogger(__name__).warning("parent process gone, exiting")
                os._exit(0)

    if chain:
        threading.Thread(target=loop, daemon=True).start()


def main() -> None:
    parser = argparse.ArgumentParser(prog="jarvis")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--token", default="")
    parser.add_argument("--no-parent-watch", action="store_true")
    args = parser.parse_args()

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    _setup_logging()
    if not args.no_parent_watch:
        _watch_parents()

    token = args.token or secrets.token_urlsafe(16)
    if not args.token:
        print(f"no --token given; using {token}", file=sys.stderr, flush=True)

    from .core import Core
    from .server import run_server

    async def runner() -> None:
        core = Core()
        await run_server(core, args.port, token)

    try:
        asyncio.run(runner())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
