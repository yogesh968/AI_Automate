"""Open / quit apps on macOS, plus shortcuts for YouTube, Spotify and WhatsApp."""

from __future__ import annotations

import difflib
import time
import urllib.parse
import webbrowser
from pathlib import Path

import psutil

from ._mac import as_str, osa, osascript, run
from .base import AUTO, CONFIRM, B, S, tool

# Common spoken names -> real app names
ALIASES = {
    "chrome": "Google Chrome", "google chrome": "Google Chrome", "vs code": "Visual Studio Code",
    "vscode": "Visual Studio Code", "code": "Visual Studio Code", "terminal": "Terminal", "iterm": "iTerm",
    "finder": "Finder", "files": "Finder", "file explorer": "Finder", "settings": "System Settings",
    "system preferences": "System Settings", "system settings": "System Settings", "store": "App Store",
    "app store": "App Store", "word": "Microsoft Word", "excel": "Microsoft Excel",
    "powerpoint": "Microsoft PowerPoint", "outlook": "Microsoft Outlook", "teams": "Microsoft Teams",
    "calculator": "Calculator", "calc": "Calculator", "notes": "Notes", "reminders": "Reminders",
    "calendar": "Calendar", "mail": "Mail", "messages": "Messages", "imessage": "Messages",
    "music": "Music", "apple music": "Music", "photos": "Photos", "camera": "Photo Booth", "facetime": "FaceTime",
    "maps": "Maps", "safari": "Safari", "preview": "Preview", "activity monitor": "Activity Monitor",
    "task manager": "Activity Monitor", "text editor": "TextEdit", "notepad": "TextEdit", "textedit": "TextEdit",
    "whatsapp": "WhatsApp", "spotify": "Spotify", "slack": "Slack", "zoom": "zoom.us", "firefox": "Firefox",
    "edge": "Microsoft Edge", "brave": "Brave Browser", "xcode": "Xcode", "screenshot": "Screenshot",
    "weather": "Weather", "clock": "Clock", "podcasts": "Podcasts", "books": "Books", "news": "News",
}

_APP_DIRS = [Path("/Applications"), Path("/System/Applications"), Path("/System/Applications/Utilities"),
             Path("/Applications/Utilities"), Path.home() / "Applications"]

_cache: dict[str, object] = {"t": 0.0, "apps": {}}


def _installed_apps() -> dict[str, str]:
    """name(lower) -> .app path. App folders + Spotlight (cached 10 min)."""
    if time.time() - float(_cache["t"]) < 600 and _cache["apps"]:
        return _cache["apps"]  # type: ignore[return-value]
    apps: dict[str, str] = {}
    for root in _APP_DIRS:
        if root.exists():
            for app in list(root.glob("*.app")) + list(root.glob("*/*.app")):
                apps.setdefault(app.stem.lower(), str(app))
    try:
        _, out = run(["mdfind", "kMDItemContentType == 'com.apple.application-bundle'"], timeout=20)
        for line in out.splitlines():
            if line.endswith(".app") and "/Library/" not in line and "/System/Library/" not in line:
                apps.setdefault(Path(line).stem.lower(), line)
    except Exception:
        pass
    _cache.update(t=time.time(), apps=apps)
    return apps


def _open(path_or_name: str) -> bool:
    if path_or_name.endswith(".app"):
        code, _ = run(["open", path_or_name])
    else:
        code, _ = run(["open", "-a", path_or_name])
    return code == 0


@tool("open_app", "Open/launch any installed application by name (e.g. 'chrome', 'vs code', 'spotify', 'whatsapp').",
      {"name": S("app name as the user said it")}, ["name"])
def open_app(name: str):
    key = name.strip().lower()
    apps = _installed_apps()
    target = ALIASES.get(key)
    if target and (target.lower() in apps):
        if _open(apps[target.lower()]):
            return f"opened {target}"
    if key in apps and _open(apps[key]):
        return f"opened {name}"
    if target and _open(target):
        return f"opened {target}"
    contains = [n for n in apps if key in n]
    if contains:
        best = min(contains, key=len)
        if _open(apps[best]):
            return f"opened {best}"
    close = difflib.get_close_matches(key, list(apps), n=1, cutoff=0.6)
    if close and _open(apps[close[0]]):
        return f"opened {close[0]}"
    if _open(name):
        return f"opened {name}"
    return f"couldn't find an app called '{name}'. Maybe it's not installed?"


@tool("list_installed_apps", "Search the installed apps (useful when open_app can't find something).",
      {"filter": S("optional text to filter by")})
def list_installed_apps(filter: str = ""):
    names = sorted(_installed_apps())
    if filter:
        names = [n for n in names if filter.lower() in n]
    return names[:80]


def _app_name(name: str) -> str:
    key = name.strip().lower()
    if key in ALIASES:
        return ALIASES[key]
    running = _running_app_names()
    for r in running:
        if r.lower() == key:
            return r
    for r in running:
        if key in r.lower():
            return r
    return name


def _running_app_names() -> list[str]:
    code, out = osascript('tell application "System Events" to get name of every application process '
                          "whose background only is false")
    return [s.strip() for s in out.split(",")] if code == 0 and out else []


@tool("close_app", "Quit an app politely (like Cmd+Q — it may ask to save). Set force=true to kill it.",
      {"name": S("app name"), "force": B("kill immediately, losing unsaved work")}, ["name"],
      level=lambda a: CONFIRM if a.get("force") else AUTO,
      describe=lambda a: f"Force-quit {a.get('name')} (unsaved work will be lost)")
def close_app(name: str, force: bool = False):
    app = _app_name(name)
    if force:
        killed = 0
        for p in psutil.process_iter(["pid", "name"]):
            if (p.info["name"] or "").lower() == app.lower():
                try:
                    p.kill()
                    killed += 1
                except Exception:
                    pass
        return f"force-quit {app}" if killed else f"'{app}' isn't running"
    if app not in _running_app_names():
        return f"'{app}' isn't running"
    osa(f"tell application {as_str(app)} to quit")
    return f"asked {app} to quit"


@tool("is_app_running", "Check whether an app is running.", {"name": S("app name")}, ["name"])
def is_app_running(name: str):
    app = _app_name(name)
    return "yes" if app in _running_app_names() else "no"


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
    code, _ = run(["open", "spotify:search:" + urllib.parse.quote(query)])
    if code != 0:
        webbrowser.open("https://open.spotify.com/search/" + urllib.parse.quote(query))
    return f"opened Spotify search for {query}. Say 'play' and I'll press play."


@tool("whatsapp_message", "Open WhatsApp with a message pre-filled for a phone number. The user presses send "
      "(or set send=true to press Return automatically).",
      {"phone": S("phone number with country code, e.g. +919876543210"), "text": S("message"),
       "send": B("press Return to send automatically")},
      ["phone", "text"],
      level=lambda a: CONFIRM if a.get("send") else AUTO,
      describe=lambda a: f"Send WhatsApp to {a.get('phone')}: \"{a.get('text')}\"")
def whatsapp_message(phone: str, text: str, send: bool = False):
    number = "".join(ch for ch in phone if ch.isdigit())
    code, _ = run(["open", f"whatsapp://send?phone={number}&text={urllib.parse.quote(text)}"])
    if code != 0:
        webbrowser.open(f"https://wa.me/{number}?text={urllib.parse.quote(text)}")
    if send:
        time.sleep(4)
        osa('tell application "System Events" to key code 36')  # Return
        return "message sent on WhatsApp"
    return "WhatsApp opened with the message ready — press Return to send"
