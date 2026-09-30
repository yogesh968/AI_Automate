"""End-to-end smoke test: start the engine, connect like the UI, send a message, print what comes back.

Usage:  .venv\\Scripts\\python.exe tests\\smoke_ws.py "open notepad"
"""

import asyncio
import json
import subprocess
import sys
import time

import websockets

PORT = 8799
TOKEN = "smoke-test-token"


async def main(text: str, seconds: float) -> None:
    proc = subprocess.Popen(
        [sys.executable, "-m", "jarvis", "--port", str(PORT), "--token", TOKEN, "--no-parent-watch"],
        stdout=subprocess.PIPE, text=True,
    )
    line = proc.stdout.readline().strip()
    print("engine said:", line)
    try:
        # wrong token must be rejected
        try:
            async with websockets.connect(f"ws://127.0.0.1:{PORT}/?token=wrong") as bad:
                await bad.recv()
            print("FAIL: bad token accepted")
        except websockets.ConnectionClosed as exc:
            print("bad token rejected:", exc.rcvd.code if exc.rcvd else exc)

        async with websockets.connect(f"ws://127.0.0.1:{PORT}/?token={TOKEN}", max_size=16 * 2**20) as ws:
            hello = json.loads(await ws.recv())
            print("hello:", {k: hello[k] for k in ("version", "platform", "keys", "state")})
            await ws.send(json.dumps({"type": "text", "text": text}))
            end = time.time() + seconds
            while time.time() < end:
                try:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=end - time.time()))
                except asyncio.TimeoutError:
                    break
                if msg["type"] == "audio":
                    print(f"audio seq={msg['seq']} bytes={len(msg['data']) * 3 // 4} text={msg['text']!r}")
                    await ws.send(json.dumps({"type": "audio_state", "playing": False}))
                elif msg["type"] == "confirm_request":
                    print("confirm_request:", msg["description"], "-> answering NO")
                    await ws.send(json.dumps({"type": "confirm_response", "id": msg["id"], "approved": False}))
                elif msg["type"] != "mic_level":
                    print(json.dumps(msg, ensure_ascii=False)[:300])
                if msg["type"] == "assistant_done":
                    await asyncio.sleep(1)
                    break
    finally:
        proc.terminate()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "hello jarvis", float(sys.argv[2]) if len(sys.argv) > 2 else 40))
