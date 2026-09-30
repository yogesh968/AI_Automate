"""Small macOS helpers shared by tool modules."""

from __future__ import annotations

import shutil
import subprocess


def run(args: list[str], timeout: int = 30, input_text: str | None = None) -> tuple[int, str]:
    proc = subprocess.run(
        args, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, input=input_text,
    )
    return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()


def osascript(script: str, timeout: int = 30, jxa: bool = False) -> tuple[int, str]:
    """Run AppleScript (or JavaScript for Automation when jxa=True); return (exit_code, output)."""
    args = ["osascript"] + (["-l", "JavaScript"] if jxa else []) + ["-"]
    return run(args, timeout=timeout, input_text=script)


def osa(script: str, timeout: int = 30) -> str:
    """Run AppleScript and raise with a readable message if it fails."""
    code, out = osascript(script, timeout=timeout)
    if code != 0:
        if "-1743" in out or "Not authorized" in out:
            raise PermissionError("macOS blocked this. Allow Jarvis in System Settings → Privacy & Security → "
                                  "Automation (and Accessibility), then try again.")
        if "-25211" in out or "assistive access" in out.lower():
            raise PermissionError("Jarvis needs Accessibility access: System Settings → Privacy & Security → "
                                  "Accessibility → enable Jarvis.")
        raise RuntimeError(out or f"osascript exit {code}")
    return out


def as_str(text: str) -> str:
    """Quote a Python string as an AppleScript string literal."""
    return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"') + '"'


def has(cmd: str) -> bool:
    return shutil.which(cmd) is not None or any(
        shutil.which(cmd, path=p) for p in ("/opt/homebrew/bin", "/usr/local/bin")
    )


def which(cmd: str) -> str | None:
    return shutil.which(cmd) or shutil.which(cmd, path="/opt/homebrew/bin") or shutil.which(cmd, path="/usr/local/bin")


def clip(text: str, limit: int = 6000) -> str:
    return text if len(text) <= limit else text[:limit] + f"\n…[{len(text) - limit} more characters]"
