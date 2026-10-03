"""Pick the tools to send with a request.

All ~100 tool schemas together are ~8k tokens — on Groq's free tier (8k tokens/minute per model) that
throttles almost every turn. So each request carries a small core set plus the groups the user's
words point at, and the model can pull in any other group itself with `load_tools`.
"""

from __future__ import annotations

import re
from typing import Any

from ..tools.base import REGISTRY

# Always sent: the everyday voice commands.
CORE_TOOLS = {
    "open_app", "close_app", "play_youtube", "spotify_search", "open_url", "web_search", "weather",
    "get_volume", "set_volume", "change_volume", "mute", "media_control", "get_datetime", "battery_status",
    "system_info", "lock_screen", "show_hud", "hide_hud", "remember", "recall",
}
CORE = "core"

# group (the rest of a tool module) -> what it is (shown to the model) and words that pull it in
GROUPS: dict[str, tuple[str, str]] = {
    "apps": ("more app tools: search installed apps, is an app running, WhatsApp messages",
             r"app|install|running|whatsapp|message|msg|chal raha"),
    "system": ("Mac controls: brightness, Wi-Fi, Bluetooth, shutdown/restart/sleep, dark/light appearance, "
               "wallpaper, System Settings panes, processes, clipboard, Trash",
               r"bright|roshni|wi-?fi|internet|bluetooth|shut ?down|restart|sleep|power|theme|dark|light|"
               r"wallpaper|setting|process|task|ram|cpu|clipboard|copy|paste|trash|recycle|kachra"),
    "mac_apps": ("Apple apps: Notes, Reminders, Calendar, iMessage, Music, reveal in Finder, notifications",
                 r"note|reminder|calendar|imessage|message|music|song|gaana|gana|finder|notification|apple"),
    "web": ("news and reading web pages", r"news|khabar|article|read|padh|summar|webpage|link"),
    "memory_tools": ("long-term memory: list or forget remembered facts", r"memor|forget|bhool"),
    "files": ("files and folders: list, search, read, write, move, copy, delete, organize",
              r"file|folder|download|document|desktop|pdf|docx|excel|photo|image|delete|move|copy|rename|"
              r"organi[sz]e|फ़ाइल|फाइल|फोल्डर|फ़ोल्डर"),
    "browser": ("drive a web page in the browser: open, read, click, fill forms, press keys",
                r"browser|website|web ?page|site|login|form"),
    "google_services": ("Gmail and Google Calendar",
                        r"g?mail|e-?mail|inbox|calendar|meeting|event|schedule|मेल"),
    "input_control": ("keyboard and mouse: type text, press keys, click, move, scroll",
                      r"type|likh|press|key|shortcut|mouse|click|scroll|cursor|enter|लिख"),
    "screen": ("look at the screen, click on what's visible, screenshots",
               r"screen|screenshot|this|yeh|\bye\b|isko|dekh|look|see|स्क्रीन|देख"),
    "shell": ("run a shell / Terminal command",
              r"command|shell|terminal|zsh|bash|script|\bpip\b|\bnpm\b|\bgit\b|\bbrew\b"),
    "mac_ui": ("windows and app UI: list/switch/minimize/full-screen windows, Spaces, click buttons in apps",
               r"window|minimi[sz]e|maximi[sz]e|full ?screen|switch|desktop|space|button|menu|tab|focus"),
    "reminders": ("reminders and timers", r"remind|timer|alarm|yaad|baje|minute|ghante|रिमाइंड|याद"),
    "routines": ("saved routines like 'good morning' or 'work mode'",
                 r"routine|mode|good morning|good night|subah"),
    "hud": ("HUD", r"hud"),
}

LOADER = {
    "type": "function",
    "function": {
        "name": "load_tools",
        "description": "Load more tools when none of your current tools fit the job. Groups: "
                       + "; ".join(f"{g} = {d}" for g, (d, _) in GROUPS.items() if g != "hud"),
        "parameters": {
            "type": "object",
            "properties": {"groups": {"type": "array", "items": {"type": "string", "enum": list(GROUPS)}}},
            "required": ["groups"],
        },
    },
}

_PATTERNS = {g: re.compile(p, re.I) for g, (_, p) in GROUPS.items()}

# Groups used in the last turn stay loaded for the next one ("haan, delete karo").
_recent: set[str] = set()


def group_of(tool_name: str) -> str:
    if tool_name in CORE_TOOLS:
        return CORE
    tool = REGISTRY.get(tool_name)
    return tool.func.__module__.rsplit(".", 1)[-1] if tool else ""


def pick_groups(text: str) -> set[str]:
    groups = {CORE} | _recent
    groups |= {g for g, pat in _PATTERNS.items() if pat.search(text)}
    return groups


def schemas(groups: set[str]) -> list[dict[str, Any]]:
    out = [t.schema() for t in REGISTRY.values() if group_of(t.name) in groups]
    if any(g not in groups for g in GROUPS):
        out.append(LOADER)
    return out


def remember_used(groups: set[str]) -> None:
    _recent.clear()
    _recent.update(g for g in groups if g != CORE)
