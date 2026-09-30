"""System control on macOS: volume, brightness, media, power, Wi-Fi/Bluetooth, appearance, info."""

from __future__ import annotations

import datetime as dt
import platform
import re
import subprocess
import time
import webbrowser

import psutil

from ._mac import as_str, osa, osascript, run, which
from .base import AUTO, CONFIRM, B, E, I, S, tool

# ---------------------------------------------------------------- volume


def _vol_settings() -> dict:
    out = osa("get volume settings")
    # "output volume:38, input volume:75, alert volume:100, output muted:false"
    vol = re.search(r"output volume:(\w+)", out)
    muted = re.search(r"output muted:(\w+)", out)
    return {"volume": int(vol.group(1)) if vol and vol.group(1).isdigit() else None,
            "muted": (muted.group(1) == "true") if muted else None}


@tool("get_volume", "Get the current speaker volume (0-100) and mute state.")
def get_volume():
    return _vol_settings()


@tool("set_volume", "Set speaker volume to an exact level 0-100.", {"level": I("0-100")}, ["level"])
def set_volume(level: int):
    level = max(0, min(100, int(level)))
    osa(f"set volume output volume {level}" + (" without output muted" if level > 0 else ""))
    return f"volume set to {level}"


@tool("change_volume", "Raise or lower volume by a relative amount (e.g. +10 or -20).",
      {"delta": I("change in percent, negative to lower")}, ["delta"])
def change_volume(delta: int):
    now = _vol_settings().get("volume") or 0
    new = max(0, min(100, now + int(delta)))
    osa(f"set volume output volume {new}")
    return f"volume {now} -> {new}"


@tool("mute", "Mute or unmute the speakers.", {"muted": B("true to mute, false to unmute")}, ["muted"])
def mute(muted: bool):
    osa("set volume with output muted" if muted else "set volume without output muted")
    return "muted" if muted else "unmuted"


# ---------------------------------------------------------------- brightness
# `brightness` CLI (brew install brightness) gives exact control; otherwise we press the
# brightness keys (16 steps from 0 to 100).


@tool("get_brightness", "Get screen brightness (0-100). Needs the `brightness` tool (brew install brightness).")
def get_brightness():
    exe = which("brightness")
    if not exe:
        return "can't read brightness without the `brightness` tool (brew install brightness)"
    _, out = run([exe, "-l"])
    m = re.search(r"brightness ([0-9.]+)", out)
    return {"brightness": round(float(m.group(1)) * 100) if m else None}


@tool("set_brightness", "Set screen brightness 0-100.", {"level": I("0-100")}, ["level"])
def set_brightness(level: int):
    level = max(0, min(100, int(level)))
    exe = which("brightness")
    if exe:
        run([exe, str(level / 100)])
        return f"brightness set to {level}"
    # key code 145 = brightness down, 144 = brightness up
    steps_up = round(level / 6.25)
    osa('tell application "System Events"\nrepeat 16 times\nkey code 145\ndelay 0.02\nend repeat\n'
        f"repeat {steps_up} times\nkey code 144\ndelay 0.02\nend repeat\nend tell")
    return f"brightness set to about {level}"


# ---------------------------------------------------------------- media keys

_NX = {"play_pause": 16, "next": 17, "previous": 18}


def _media_key(key: int) -> None:
    from AppKit import NSEvent
    from Quartz import CGEventPost, kCGHIDEventTap

    for down in (True, False):
        ev = NSEvent.otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2_(
            14, (0, 0), 0xA00 if down else 0xB00, 0, 0, 0, 8, (key << 16) | ((0xA if down else 0xB) << 8), -1)
        CGEventPost(kCGHIDEventTap, ev.CGEvent())
        time.sleep(0.02)


@tool("media_control", "Control music/video playback in any player (Spotify, Apple Music, YouTube in browser…).",
      {"action": E("what to do", ["play_pause", "next", "previous", "stop"])}, ["action"])
def media_control(action: str):
    _media_key(_NX.get(action, 16))
    return f"media {action}"


# ---------------------------------------------------------------- power

_pending_power: dict[str, subprocess.Popen | None] = {"proc": None}


@tool("lock_screen", "Lock the Mac.")
def lock_screen():
    code, _ = osascript('tell application "System Events" to keystroke "q" using {control down, command down}')
    if code != 0:
        run(["pmset", "displaysleepnow"])
    return "locked"


def _power_describe(a):
    return f"{a.get('action')} the Mac" + (f" in {a.get('delay_seconds', 0)}s" if a.get("delay_seconds") else "")


@tool("power", "Sleep, shut down, restart or log out. Use cancel_shutdown to abort a delayed shutdown/restart.",
      {"action": E("power action", ["sleep", "shutdown", "restart", "sign_out", "cancel_shutdown"]),
       "delay_seconds": I("delay before shutdown/restart, default 10")},
      ["action"],
      level=lambda a: AUTO if a.get("action") == "cancel_shutdown" else CONFIRM,
      describe=_power_describe)
def power(action: str, delay_seconds: int = 10):
    if action == "cancel_shutdown":
        proc = _pending_power.get("proc")
        if proc and proc.poll() is None:
            proc.kill()
            _pending_power["proc"] = None
            return "pending shutdown/restart cancelled"
        return "nothing pending to cancel"
    if action == "sleep":
        run(["pmset", "sleepnow"])
        return "going to sleep"
    verb = {"shutdown": "shut down", "restart": "restart", "sign_out": "log out"}[action]
    script = f'tell application "System Events" to {verb}'
    delay = max(0, int(delay_seconds))
    if delay and action != "sign_out":
        _pending_power["proc"] = subprocess.Popen(
            ["/bin/sh", "-c", f"sleep {delay}; osascript -e {_shq(script)}"], start_new_session=True)
        return f"{action} in {delay} seconds (say 'cancel shutdown' to stop it)"
    osa(script)
    return f"{action} requested"


def _shq(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


# ---------------------------------------------------------------- radios


def _wifi_device() -> str:
    _, out = run(["networksetup", "-listallhardwareports"])
    m = re.search(r"Hardware Port: (?:Wi-Fi|AirPort)\s*\nDevice: (\w+)", out)
    return m.group(1) if m else "en0"


@tool("wifi", "Turn Wi-Fi on/off or check its status and connected network.",
      {"action": E("action", ["on", "off", "status"])}, ["action"])
def wifi(action: str):
    dev = _wifi_device()
    if action == "status":
        _, power_state = run(["networksetup", "-getairportpower", dev])
        _, net = run(["networksetup", "-getairportnetwork", dev])
        return f"{power_state}. {net}"
    code, out = run(["networksetup", "-setairportpower", dev, action])
    return f"wifi {action}" if code == 0 else f"couldn't switch Wi-Fi: {out}"


@tool("bluetooth", "Turn Bluetooth on/off or check its status (needs `blueutil`: brew install blueutil).",
      {"action": E("action", ["on", "off", "status"])}, ["action"])
def bluetooth(action: str):
    exe = which("blueutil")
    if not exe:
        run(["open", "x-apple.systempreferences:com.apple.preferences.Bluetooth"])
        return "blueutil isn't installed, so I opened Bluetooth settings (brew install blueutil for direct control)"
    if action == "status":
        _, out = run([exe, "-p"])
        return "bluetooth is " + ("on" if out.strip() == "1" else "off")
    run([exe, "-p", "1" if action == "on" else "0"])
    return f"bluetooth {action}"


# ---------------------------------------------------------------- settings / appearance / wallpaper

SETTINGS_PAGES = {
    "display": "com.apple.preference.displays", "sound": "com.apple.preference.sound",
    "wifi": "com.apple.preference.network", "network": "com.apple.preference.network",
    "bluetooth": "com.apple.preferences.Bluetooth", "battery": "com.apple.preference.battery",
    "update": "com.apple.preferences.softwareupdate", "notifications": "com.apple.preference.notifications",
    "privacy": "com.apple.preference.security", "security": "com.apple.preference.security",
    "background": "com.apple.preference.desktopscreeneffect", "wallpaper": "com.apple.Wallpaper-Settings.extension",
    "appearance": "com.apple.preference.general", "general": "com.apple.preference.general",
    "keyboard": "com.apple.preference.keyboard", "trackpad": "com.apple.preference.trackpad",
    "mouse": "com.apple.preference.mouse", "date": "com.apple.preference.datetime",
    "language": "com.apple.Localization", "storage": "com.apple.settings.Storage",
    "users": "com.apple.preferences.users", "focus": "com.apple.Focus-Settings.extension",
    "accessibility": "com.apple.preference.universalaccess", "home": "",
}


@tool("open_settings", "Open a System Settings page.", {"page": E("which page", sorted(SETTINGS_PAGES))}, ["page"])
def open_settings(page: str):
    pane = SETTINGS_PAGES.get(page, "")
    run(["open", f"x-apple.systempreferences:{pane}" if pane else "/System/Applications/System Settings.app"])
    return f"opened {page} settings"


@tool("set_theme", "Switch macOS between dark and light mode.", {"mode": E("theme", ["dark", "light"])}, ["mode"])
def set_theme(mode: str):
    osa('tell application "System Events" to tell appearance preferences to set dark mode to '
        + ("true" if mode == "dark" else "false"))
    return f"{mode} mode on"


@tool("set_wallpaper", "Set the desktop wallpaper (all screens) to an image file.", {"path": S("image file path")},
      ["path"])
def set_wallpaper(path: str):
    from ..safety.paths import resolve

    p = resolve(path)
    if not p.exists():
        return f"file not found: {p}"
    osa(f'tell application "System Events" to tell every desktop to set picture to POSIX file {as_str(str(p))}')
    return f"wallpaper set to {p.name}"


@tool("empty_recycle_bin", "Permanently empty the Trash.", level=CONFIRM,
      describe=lambda a: "Permanently empty the Trash")
def empty_recycle_bin():
    osa('tell application "Finder" to empty trash', timeout=120)
    return "trash emptied"


# ---------------------------------------------------------------- info


@tool("get_datetime", "Get the current local date, time and day of week.")
def get_datetime():
    now = dt.datetime.now().astimezone()
    return now.strftime("%A, %d %B %Y, %I:%M %p (%Z)")


@tool("system_info", "CPU, RAM, disk, battery, uptime and macOS version of this Mac.")
def system_info():
    vm = psutil.virtual_memory()
    disks = []
    for part in psutil.disk_partitions(all=False):
        if not part.mountpoint.startswith(("/System/Volumes/VM", "/System/Volumes/Preboot", "/System/Volumes/Update")):
            try:
                u = psutil.disk_usage(part.mountpoint)
                disks.append(f"{part.mountpoint} {u.free // 2**30}GB free of {u.total // 2**30}GB")
            except Exception:
                continue
    bat = psutil.sensors_battery()
    boot = dt.datetime.fromtimestamp(psutil.boot_time())
    _, chip = run(["sysctl", "-n", "machdep.cpu.brand_string"])
    return {
        "os": f"macOS {platform.mac_ver()[0]} ({platform.machine()})",
        "chip": chip,
        "machine": platform.node(),
        "cpu_percent": psutil.cpu_percent(interval=0.5),
        "cpu_cores": psutil.cpu_count(),
        "ram": f"{vm.used // 2**20}MB used of {vm.total // 2**20}MB ({vm.percent}%)",
        "disks": list(dict.fromkeys(disks)),
        "battery": None if not bat else {"percent": bat.percent, "plugged_in": bat.power_plugged,
                                         "minutes_left": None if bat.secsleft < 0 else bat.secsleft // 60},
        "uptime_hours": round((dt.datetime.now() - boot).total_seconds() / 3600, 1),
    }


@tool("battery_status", "Battery percentage and whether charging.")
def battery_status():
    bat = psutil.sensors_battery()
    if not bat:
        _, out = run(["pmset", "-g", "batt"])
        return out or "no battery (desktop Mac)"
    left = "" if bat.secsleft < 0 else f", about {bat.secsleft // 60} minutes left"
    return f"{bat.percent}%{' charging' if bat.power_plugged else ''}{left}"


@tool("top_processes", "List the processes using the most CPU or memory.",
      {"sort_by": E("sort key", ["cpu", "memory"]), "count": I("how many, default 8")})
def top_processes(sort_by: str = "memory", count: int = 8):
    procs = list(psutil.process_iter(["pid", "name", "memory_info"]))
    for p in procs:
        try:
            p.cpu_percent(None)
        except Exception:
            pass
    time.sleep(0.5)
    rows = []
    for p in procs:
        try:
            rows.append({"pid": p.pid, "name": p.info["name"], "cpu": p.cpu_percent(None),
                         "mem_mb": round(p.info["memory_info"].rss / 2**20)})
        except Exception:
            continue
    key = "cpu" if sort_by == "cpu" else "mem_mb"
    return sorted(rows, key=lambda r: r[key], reverse=True)[: max(1, min(int(count), 25))]


_CRITICAL = {"launchd", "kernel_task", "windowserver", "loginwindow", "systemuiserver", "securityd", "opendirectoryd"}


@tool("kill_process", "Force-stop a process by name or PID (unsaved work is lost).",
      {"name_or_pid": S("process name like 'Google Chrome' or a PID")}, ["name_or_pid"],
      level=CONFIRM, describe=lambda a: f"Force-stop process {a.get('name_or_pid')}")
def kill_process(name_or_pid: str):
    target = str(name_or_pid).strip().lower()
    killed = []
    for p in psutil.process_iter(["pid", "name"]):
        name = (p.info["name"] or "").lower()
        if (target.isdigit() and p.pid == int(target)) or name == target:
            if name in _CRITICAL or p.pid <= 1:
                raise PermissionError("refusing to kill a critical macOS process")
            try:
                p.kill()
                killed.append(f"{name}({p.pid})")
            except Exception as exc:
                killed.append(f"{name}({p.pid}) failed: {exc}")
    return ", ".join(killed) or "no matching process"


# ---------------------------------------------------------------- clipboard / url


@tool("clipboard_get", "Read the text currently on the clipboard.")
def clipboard_get():
    import pyperclip

    return pyperclip.paste() or "(clipboard is empty)"


@tool("clipboard_set", "Put text on the clipboard.", {"text": S("text to copy")}, ["text"])
def clipboard_set(text: str):
    import pyperclip

    pyperclip.copy(text)
    return "copied to clipboard"


@tool("open_url", "Open a website or URL in the default browser.", {"url": S("full URL or domain")}, ["url"])
def open_url(url: str):
    if "://" not in url:
        url = "https://" + url.strip()
    webbrowser.open(url)
    return f"opened {url}"
