"""Local WebSocket server the Electron UI connects to (token-protected, 127.0.0.1 only)."""

from __future__ import annotations

import hmac
import json
import logging
from urllib.parse import parse_qs, urlparse

from websockets.asyncio.server import serve

from .core import Core

log = logging.getLogger(__name__)


async def run_server(core: Core, port: int, token: str) -> None:
    async def handler(ws) -> None:
        query = parse_qs(urlparse(ws.request.path).query)
        given = (query.get("token") or [""])[0]
        if not hmac.compare_digest(given, token):
            await ws.close(code=4401, reason="bad token")
            return
        core.clients.add(ws)
        log.info("UI connected (%d client(s))", len(core.clients))
        try:
            await ws.send(json.dumps(core.hello(), ensure_ascii=False))
            await core.on_connect()
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                try:
                    await core.handle(msg)
                except Exception as exc:  # noqa: BLE001
                    log.exception("handling %s failed", msg.get("type"))
                    await core.broadcast({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
        except Exception:
            pass
        finally:
            core.clients.discard(ws)
            log.info("UI disconnected")

    async with serve(handler, "127.0.0.1", port, max_size=8 * 2**20, ping_interval=20, ping_timeout=30):
        print(f"JARVIS_READY {port}", flush=True)
        log.info("engine listening on 127.0.0.1:%d", port)
        await core.run_background()
