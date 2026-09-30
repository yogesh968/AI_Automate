"""Run PowerShell commands (always needs approval; dangerous commands are blocked)."""

from __future__ import annotations

import asyncio

from ..safety.guard import command_is_blocked
from ..safety.paths import resolve
from ._win import CREATE_NO_WINDOW, clip
from .base import BLOCKED, CONFIRM, I, S, tool


def _level(args):
    why = command_is_blocked(args.get("command", ""))
    if why:
        raise PermissionError(why)
    return CONFIRM


@tool("run_command", "Run a PowerShell command and return its output. Use for things no other tool covers "
      "(git, pip, npm, winget, network checks, scripts). Prefer dedicated tools when they exist.",
      {"command": S("PowerShell command"), "cwd": S("working folder, default home"),
       "timeout_seconds": I("default 60, max 600")},
      ["command"], level=_level, describe=lambda a: f"Run in PowerShell: {a.get('command')}")
async def run_command(command: str, cwd: str = "", timeout_seconds: int = 60):
    proc = await asyncio.create_subprocess_exec(
        "powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command",
        "[Console]::OutputEncoding=[Text.Encoding]::UTF8; " + command,
        cwd=str(resolve(cwd or "~")),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        creationflags=CREATE_NO_WINDOW,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=max(1, min(int(timeout_seconds), 600)))
    except (asyncio.TimeoutError, asyncio.CancelledError):
        proc.kill()
        raise
    text = out.decode("utf-8", errors="replace").strip()
    return f"exit code {proc.returncode}\n{clip(text, 8000) or '(no output)'}"
