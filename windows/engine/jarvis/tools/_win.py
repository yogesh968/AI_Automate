"""Small Windows helpers shared by tool modules."""

from __future__ import annotations

import subprocess

CREATE_NO_WINDOW = 0x08000000


def powershell(script: str, timeout: int = 30) -> tuple[int, str]:
    """Run a PowerShell snippet hidden; return (exit_code, combined output)."""
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=CREATE_NO_WINDOW,
    )
    out = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr.strip() else "")
    return proc.returncode, out.strip()


def run(args: list[str], timeout: int = 30) -> tuple[int, str]:
    proc = subprocess.run(
        args, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, creationflags=CREATE_NO_WINDOW,
    )
    return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()


def com_init() -> None:
    """COM must be initialised on each worker thread that uses it (pycaw, pywinauto)."""
    try:
        import comtypes

        comtypes.CoInitialize()
    except OSError:
        pass
    except Exception:
        pass


def clip(text: str, limit: int = 6000) -> str:
    return text if len(text) <= limit else text[:limit] + f"\n…[{len(text) - limit} more characters]"
