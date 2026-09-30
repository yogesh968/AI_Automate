"""Run shell commands in zsh (always needs approval; dangerous commands are blocked)."""

from __future__ import annotations

import asyncio
import os
import signal

from ..safety.guard import command_is_blocked
from ..safety.paths import resolve
from ._mac import clip
from .base import CONFIRM, I, S, tool


def _level(args):
    why = command_is_blocked(args.get("command", ""))
    if why:
        raise PermissionError(why)
    return CONFIRM


@tool("run_command", "Run a zsh command in Terminal-like fashion and return its output. Use for things no other tool "
      "covers (git, brew, pip, npm, network checks, scripts). Prefer dedicated tools when they exist.",
      {"command": S("zsh command"), "cwd": S("working folder, default home"),
       "timeout_seconds": I("default 60, max 600")},
      ["command"], level=_level, describe=lambda a: f"Run in Terminal: {a.get('command')}")
async def run_command(command: str, cwd: str = "", timeout_seconds: int = 60):
    env = dict(os.environ)
    env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + env.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
    proc = await asyncio.create_subprocess_exec(
        "/bin/zsh", "-lc", command,
        cwd=str(resolve(cwd or "~")),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        stdin=asyncio.subprocess.DEVNULL,
        env=env,
        start_new_session=True,  # own process group so we can kill children too
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=max(1, min(int(timeout_seconds), 600)))
    except (asyncio.TimeoutError, asyncio.CancelledError):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        raise
    text = out.decode("utf-8", errors="replace").strip()
    return f"exit code {proc.returncode}\n{clip(text, 8000) or '(no output)'}"
