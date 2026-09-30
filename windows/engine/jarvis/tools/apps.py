"""Open / close apps, plus shortcuts for YouTube, Spotify and WhatsApp."""

from __future__ import annotations

import difflib
import json
import os
import subprocess
import time
import urllib.parse
import webbrowser
from pathlib import Path

import psutil

from ._win import powershell
from .base import AUTO, CONFIRM, B, S, tool

# Common names -> something os.startfile / Start-Process understands.
ALIASES = {
    "notepad": "notepad.exe", "calculator": "calc.exe", "calc": "calc.exe", "paint": "mspaint.exe",
    "cmd": "cmd.exe", "command prompt": "cmd.exe", "powershell": "powershell.exe", "terminal": "wt.exe",
    "windows terminal": "wt.exe", "file explorer": "explorer.exe", "explorer": "explorer.exe",
    "files": "explorer.exe", "task manager": "taskmgr.exe", "control panel": "control.exe",
    "settings": "ms-settings:", "store": "ms-windows-store:", "microsoft store": "ms-windows-store:",
    "edge": "msedge", "microsoft edge": "msedge", "chrome": "chrome", "google chrome": "chrome",
    "firefox": "firefox", "vs code": "code", "vscode": "code", "visual studio code": "code",
    "word": "winword", "excel": "excel", "powerpoint": "powerpnt", "outlook": "outlook",
    "onenote": "onenote", "teams": "msteams:", "spotify": "spotify:", "whatsapp": "whatsapp:",
    "camera": "microsoft.windows.camera:", "photos": "ms-photos:", "mail": "outlookmail:",
    "calendar": "outlookcal:", "clock": "ms-clock:", "alarms": "ms-clock:", "snipping tool": "ms-screenclip:",
    "maps": "bingmaps:", "weather": "bingweather:", "xbox": "xbox:", "snip": "ms-screenclip:",
}

_START_MENU_DIRS = [
    Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Microsoft/Windows/Start Menu/Programs",
    Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
    Path.home() / "Desktop",
]

_cache: dict[str, object] = {"t": 0.0, "apps": {}}


def _installed_apps() -> dict[str, str]:
    """name(lower) -> launch target. Start Menu shortcuts + Store apps (cached 10 min)."""
    if time.time() - float(_cache["t"]) < 600 and _cache["apps"]:
        return _cache["apps"]  # type: ignore[return-value]
    apps: dict[str, str] = {}
    for root in _START_MENU_DIRS:
        if root.exists():
            for lnk in root.rglob("*.lnk"):
                name = lnk.stem.lower()
                if "uninstall" not in name:
                    apps.setdefault(name, str(lnk))
    try:
        code, out = powershell("Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress", timeout=20)
        if code == 0 and out:
            data = json.loads(out)
            for item in data if isinstance(data, list) else [data]:
                name = (item.get("Name") or "").lower()
                if name and item.get("AppID"):
                    apps.setdefault(name, "shell:AppsFolder\\" + item["AppID"])
    except Exception:
        pass
    _cache.update(t=time.time(), apps=apps)
    return apps


def _launch(target: str) -> None:
    if target.startswith("shell:AppsFolder"):
        subprocess.Popen(["explorer.exe", target])
    else:
        os.startfile(target)


@tool("open_app", "Open/launch any installed application by name (e.g. 'chrome', 'vs code', 'spotify', 'whatsapp').",
      {"name": S("app name as the user said it")}, ["name"])
def open_app(name: str):
    key = name.strip().lower()
    apps = _installed_apps()
    if key in apps:
        _launch(apps[key])
        return f"opened {name}"
    if key in ALIASES:
        target = ALIASES[key]
        try:
            os.startfile(target)
            return f"opened {name}"
        except OSError:
            pass
    # fuzzy match on installed apps: exact word containment first, then similarity
    contains = [n for n in apps if key in n]
    if contains:
        best = min(contains, key=len)
        _launch(apps[best])
        return f"opened {best}"
    close = difflib.get_close_matches(key, list(apps), n=1, cutoff=0.6)
    if close:
        _launch(apps[close[0]])
        return f"opened {close[0]}"
    try:
        os.startfile(key)
        return f"opened {name}"
    except OSError:
        return f"couldn't find an app called '{name}'. Maybe it's not installed?"


@tool("list_installed_apps", "Search the installed apps (useful when open_app can't find something).",
      {"filter": S("optional text to filter by")})
def list_installed_apps(filter: str = ""):
    names = sorted(_installed_apps())
    if filter:
        names = [n for n in names if filter.lower() in n]
    return names[:80]


def _matching_windows(name: str):
    import pygetwindow as gw

    key = name.lower()
    return [w for w in gw.getAllWindows() if w.title and key in w.title.lower()]


def _matching_procs(name: str):
    key = name.lower().removesuffix(".exe")
    key = {"vs code": "code", "vscode": "code", "word": "winword", "powerpoint": "powerpnt",
           "edge": "msedge", "file explorer": "explorer"}.get(key, key)
    out = []
    for p in psutil.process_iter(["pid", "name"]):
        pname = (p.info["name"] or "").lower().removesuffix(".exe")
        if pname == key or (len(key) > 3 and key in pname):
            out.append(p)
    return out


@tool("close_app", "Close an app politely (like clicking X — it may ask to save). Set force=true to kill it.",
      {"name": S("app or window name"), "force": B("kill immediately, losing unsaved work")}, ["name"],
      level=lambda a: CONFIRM if a.get("force") else AUTO,
      describe=lambda a: f"Force-kill {a.get('name')} (unsaved work will be lost)")
def close_app(name: str, force: bool = False):
    if force:
        procs = _matching_procs(name)
        for p in procs:
            try:
                p.kill()
            except Exception:
                pass
        return f"killed {len(procs)} process(es)" if procs else f"'{name}' isn't running"
    wins = _matching_windows(name)
    if not wins:
        procs = _matching_procs(name)
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass
        return f"closed {len(procs)} process(es)" if procs else f"'{name}' isn't running"
    for w in wins:
        try:
            w.close()
        except Exception:
            pass
    return f"asked {len(wins)} window(s) to close"


@tool("is_app_running", "Check whether an app is running.", {"name": S("app name")}, ["name"])
def is_app_running(name: str):
    procs = _matching_procs(name)
    return f"yes, {len(procs)} process(es)" if procs else "no"


# ---------------------------------------------------------------- media / messaging shortcuts


@tool("play_youtube", "Search YouTube and play the top video (songs, trailers, tutorials…).",
      {"query": S("what to play")}, ["query"])
def play_youtube(query: str):
    url = None
    try:
        from ddgs import DDGS

        for r in DDGS().videos(f"{query} youtube", max_results=5):
            content = r.get("content") or r.get("url") or ""
            if "youtube.com/watch" in content or "youtu.be/" in content:
                url = content
                break
    except Exception:
        pass
    url = url or "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
    webbrowser.open(url)
    return f"playing on YouTube: {url}"


@tool("spotify_search", "Open Spotify with a search for a song, artist or playlist.",
      {"query": S("song / artist / playlist")}, ["query"])
def spotify_search(query: str):
    try:
        os.startfile("spotify:search:" + urllib.parse.quote(query))
    except OSError:
        webbrowser.open("https://open.spotify.com/search/" + urllib.parse.quote(query))
    return f"opened Spotify search for {query}. Say 'play' and I'll press play."


@tool("whatsapp_message", "Open WhatsApp with a message pre-filled for a phone number. The user presses send "
      "(or set send=true to press Enter automatically).",
      {"phone": S("phone number with country code, e.g. +919876543210"), "text": S("message"),
       "send": B("press Enter to send automatically")},
      ["phone", "text"],
      level=lambda a: CONFIRM if a.get("send") else AUTO,
      describe=lambda a: f"Send WhatsApp to {a.get('phone')}: \"{a.get('text')}\"")
def whatsapp_message(phone: str, text: str, send: bool = False):
    number = "".join(ch for ch in phone if ch.isdigit())
    uri = f"whatsapp://send?phone={number}&text={urllib.parse.quote(text)}"
    try:
        os.startfile(uri)
    except OSError:
        webbrowser.open(f"https://wa.me/{number}?text={urllib.parse.quote(text)}")
    if send:
        import pyautogui

        time.sleep(4)
        pyautogui.press("enter")
        return "message sent on WhatsApp"
    return "WhatsApp opened with the message ready — press Enter to send"
