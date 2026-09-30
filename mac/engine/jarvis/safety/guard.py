"""Decides whether a tool call runs now, needs the user's OK, or is refused."""

from __future__ import annotations

import re
from typing import Any

from ..tools.base import AUTO, BLOCKED, CONFIRM, Tool

# Commands that can wreck the Mac. Matched case-insensitively against shell commands.
BLOCKED_COMMAND_PATTERNS = [
    r"\brm\s+(-[a-z]*\s+)*-[a-z]*[rf][a-z]*\s+(-[a-z]*\s+)*(/|~|\$home|/\*|~/\*)(\s|$|;|&)",
    r"\brm\s+(-[a-z]*\s+)*-[a-z]*[rf][a-z]*\s+.*\s(/system|/library|/usr|/bin|/sbin|/private|/etc|/applications)\b",
    r"\bsudo\s+rm\b",
    r"\bdiskutil\s+(erase\w*|zerodisk|secureerase|partitiondisk|reformat|apfs\s+delete\w*)",
    r"\bmkfs\b",
    r"\bnewfs_\w+",
    r"\bdd\b.*\bof=/dev/",
    r">\s*/dev/(r?disk|sd)",
    r"\bcsrutil\b",
    r"\bnvram\b",
    r"\bspctl\s+--master-disable",
    r"\bspctl\s+--global-disable",
    r"\blaunchctl\s+(unload|bootout|remove|disable)\b.*\b(system|/library/launchdaemons|com\.apple)",
    r"\bchmod\s+(-[a-z]*\s+)*-?r\w*\s+[0-7]*777\s+/(\s|$)",
    r"\bchown\s+-r\b.*\s/(\s|$)",
    r":\(\)\s*\{\s*:\|:&\s*\};:",
    r"\b(curl|wget)\b[^|]*\|\s*(sudo\s+)?(ba|z|da)?sh\b",
    r"\btmutil\s+(delete|disable)",
    r"\bsecurity\s+delete-(keychain|generic-password|internet-password|certificate)",
    r"\bsecurity\s+(find-generic-password|find-internet-password|dump-keychain)\b.*(-w|-g|-d)",
    r"\bdscl\b.*\s-(delete|passwd)",
    r"\bsysadminctl\b.*(-deleteuser|-resetpasswordfor)",
    r"\bfdesetup\b",
    r"\bkillall\s+(-9\s+)?(windowserver|loginwindow|launchd|kernel_task)\b",
    r"\bpfctl\b.*-d\b",
    r"\bsoftwareupdate\b.*--ignore",
    r"\bxattr\s+-(r?)d\s+com\.apple\.quarantine\b.*\s/(applications|system)",
    r"\bbase64\s+(-d|--decode)\b.*\|\s*(ba|z)?sh\b",
    r"\bosascript\b.*do shell script.*with administrator privileges",
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
