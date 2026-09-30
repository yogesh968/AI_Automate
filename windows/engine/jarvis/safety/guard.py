"""Decides whether a tool call runs now, needs the user's OK, or is refused."""

from __future__ import annotations

import re
from typing import Any

from ..tools.base import AUTO, BLOCKED, CONFIRM, Tool

# Commands that can wreck the machine. Matched case-insensitively against shell commands.
BLOCKED_COMMAND_PATTERNS = [
    r"\bformat(-volume)?\b\s+[a-z]:?",
    r"\bdiskpart\b",
    r"\bbcdedit\b",
    r"\bcipher\s+/w",
    r"\bvssadmin\b.*\bdelete\b",
    r"\bwbadmin\b.*\bdelete\b",
    r"\breg(\.exe)?\s+delete\s+hklm",
    r"remove-item\b.*hklm:",
    r"\bclear-disk\b",
    r"\binitialize-disk\b",
    r"\bremove-partition\b",
    r"\bset-executionpolicy\b\s+unrestricted",
    r"\bdel\b.*\s/s\b.*[a-z]:\\(windows|program files)",
    r"\brd\b.*\s/s\b.*[a-z]:\\\s*$",
    r"remove-item\b.*-recurse\b.*\b[a-z]:\\(\s|$|\*|windows|program)",
    r"\btakeown\b.*[a-z]:\\windows",
    r"\bicacls\b.*[a-z]:\\windows",
    r"\bnet\s+user\b.*\s/delete",
    r"\bmimikatz\b",
    r"\bschtasks\b.*/create.*\\system32",
    r"\bdisable-computerrestore\b",
    r"-encodedcommand\b",
    r"\biex\b.*\b(downloadstring|invoke-webrequest|iwr)\b",
    r"\brm\s+-rf\s+/",
]
_BLOCKED_RE = [re.compile(p, re.IGNORECASE) for p in BLOCKED_COMMAND_PATTERNS]


def command_is_blocked(command: str) -> str | None:
    for rx in _BLOCKED_RE:
        if rx.search(command or ""):
            return f"command matches a blocked pattern ({rx.pattern})"
    return None


class Decision:
    def __init__(self, level: str, reason: str = "") -> None:
        self.level = level
        self.reason = reason


def decide(tool: Tool, args: dict[str, Any]) -> Decision:
    try:
        level = tool.level_for(args)
    except PermissionError as exc:
        return Decision(BLOCKED, str(exc))
    except Exception as exc:  # a broken level function must not open the gates
        return Decision(CONFIRM, f"could not classify: {exc}")
    if level not in (AUTO, CONFIRM, BLOCKED):
        level = CONFIRM
    return Decision(level)
