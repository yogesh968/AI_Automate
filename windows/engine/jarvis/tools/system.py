"""System control: volume, brightness, media, power, Wi-Fi/Bluetooth, theme, info."""

from __future__ import annotations

import ctypes
import datetime as dt
import os
import platform
import time
import webbrowser

import psutil

from ._win import com_init, powershell, run
from .base import AUTO, CONFIRM, B, E, I, S, tool

# ---------------------------------------------------------------- volume


def _endpoint():
    com_init()
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    speakers = AudioUtilities.GetSpeakers()
    ev = getattr(speakers, "EndpointVolume", None)  # newer pycaw
    if ev is not None:
        return ev
    from ctypes import POINTER, cast

    from comtypes import CLSCTX_ALL

    iface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(iface, POINTER(IAudioEndpointVolume))


@tool("get_volume", "Get the current speaker volume (0-100) and mute state.")
def get_volume():
    ev = _endpoint()
    return {"volume": round(ev.GetMasterVolumeLevelScalar() * 100), "muted": bool(ev.GetMute())}


@tool("set_volume", "Set speaker volume to an exact level 0-100.", {"level": I("0-100")}, ["level"])
def set_volume(level: int):
    ev = _endpoint()
    level = max(0, min(100, int(level)))
    ev.SetMasterVolumeLevelScalar(level / 100, None)
    if level > 0:
        ev.SetMute(0, None)
    return f"volume set to {level}"


@tool("change_volume", "Raise or lower volume by a relative amount (e.g. +10 or -20).",
      {"delta": I("change in percent, negative to lower")}, ["delta"])
def change_volume(delta: int):
    ev = _endpoint()
    now = ev.GetMasterVolumeLevelScalar() * 100
    new = max(0, min(100, round(now + int(delta))))
    ev.SetMasterVolumeLevelScalar(new / 100, None)
    return f"volume {round(now)} -> {new}"


@tool("mute", "Mute or unmute the speakers.", {"muted": B("true to mute, false to unmute")}, ["muted"])
def mute(muted: bool):
    _endpoint().SetMute(1 if muted else 0, None)
    return "muted" if muted else "unmuted"


# ---------------------------------------------------------------- brightness


@tool("get_brightness", "Get screen brightness (0-100).")
def get_brightness():
    import screen_brightness_control as sbc

    return {"brightness": sbc.get_brightness()}


@tool("set_brightness", "Set screen brightness 0-100 (works on laptops / DDC monitors).",
      {"level": I("0-100")}, ["level"])
def set_brightness(level: int):
    import screen_brightness_control as sbc

    level = max(0, min(100, int(level)))
    sbc.set_brightness(level)
    return f"brightness set to {level}"


# ---------------------------------------------------------------- media


@tool("media_control", "Control music/video playback in any player (Spotify, YouTube, etc.).",
      {"action": E("what to do", ["play_pause", "next", "previous", "stop"])}, ["action"])
def media_control(action: str):
    import pyautogui

    key = {"play_pause": "playpause", "next": "nexttrack", "previous": "prevtrack", "stop": "stop"}[action]
    pyautogui.press(key)
    return f"media {action}"


# ---------------------------------------------------------------- power


@tool("lock_screen", "Lock the PC.")
def lock_screen():
    ctypes.windll.user32.LockWorkStation()
    return "locked"


def _power_describe(a):
    return f"{a.get('action')} the computer" + (f" in {a.get('delay_seconds', 0)}s" if a.get("delay_seconds") else "")


@tool("power", "Sleep, shut down, restart or sign out. Use cancel_shutdown to abort a pending shutdown.",
      {"action": E("power action", ["sleep", "shutdown", "restart", "sign_out", "cancel_shutdown"]),
       "delay_seconds": I("delay before shutdown/restart, default 10")},
      ["action"],
      level=lambda a: AUTO if a.get("action") == "cancel_shutdown" else CONFIRM,
      describe=_power_describe)
def power(action: str, delay_seconds: int = 10):
    delay = max(0, int(delay_seconds))
    if action == "sleep":
        run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
    elif action == "shutdown":
        run(["shutdown", "/s", "/t", str(delay)])
    elif action == "restart":
        run(["shutdown", "/r", "/t", str(delay)])
    elif action == "sign_out":
        run(["shutdown", "/l"])
    elif action == "cancel_shutdown":
        run(["shutdown", "/a"])
    return f"{action} requested"


# ---------------------------------------------------------------- radios (wifi / bluetooth)

_RADIO_PS = r"""
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | ? { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
Function Await($op, $type) { $t = $asTask.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result }
[Windows.Devices.Radios.Radio,Windows.System.Devices,ContentType=WindowsRuntime] | Out-Null
[Windows.Devices.Radios.RadioAccessStatus,Windows.System.Devices,ContentType=WindowsRuntime] | Out-Null
Await ([Windows.Devices.Radios.Radio]::RequestAccessAsync()) ([Windows.Devices.Radios.RadioAccessStatus]) | Out-Null
$radios = Await ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]])
$r = $radios | ? { $_.Kind -eq '__KIND__' } | Select-Object -First 1
if (-not $r) { Write-Output 'NO_RADIO'; exit 0 }
if ('__STATE__' -ne 'Query') {
  [Windows.Devices.Radios.RadioState,Windows.System.Devices,ContentType=WindowsRuntime] | Out-Null
  Await ($r.SetStateAsync('__STATE__')) ([Windows.Devices.Radios.RadioAccessStatus]) | Out-Null
}
Write-Output $r.State
"""


def _radio(kind: str, state: str) -> str:
    code, out = powershell(_RADIO_PS.replace("__KIND__", kind).replace("__STATE__", state), timeout=20)
    return out.splitlines()[-1] if out else f"exit {code}"


@tool("wifi", "Turn Wi-Fi on/off or check its status and connected network.",
      {"action": E("action", ["on", "off", "status"])}, ["action"])
def wifi(action: str):
    if action == "status":
        _, out = run(["netsh", "wlan", "show", "interfaces"])
        return out[:1500] or _radio("WiFi", "Query")
    result = _radio("WiFi", "On" if action == "on" else "Off")
    if result == "NO_RADIO" or result.startswith("exit"):
        os.startfile("ms-settings:network-wifi")
        return "couldn't toggle directly, opened Wi-Fi settings"
    return f"wifi is {result}"


@tool("bluetooth", "Turn Bluetooth on/off or check its status.",
      {"action": E("action", ["on", "off", "status"])}, ["action"])
def bluetooth(action: str):
    state = {"on": "On", "off": "Off", "status": "Query"}[action]
    result = _radio("Bluetooth", state)
    if result == "NO_RADIO" or result.startswith("exit"):
        os.startfile("ms-settings:bluetooth")
        return "couldn't toggle directly, opened Bluetooth settings"
    return f"bluetooth is {result}"


# ---------------------------------------------------------------- settings pages / theme / wallpaper

SETTINGS_PAGES = {
    "display": "ms-settings:display", "sound": "ms-settings:sound", "wifi": "ms-settings:network-wifi",
    "bluetooth": "ms-settings:bluetooth", "battery": "ms-settings:batterysaver", "update": "ms-settings:windowsupdate",
    "apps": "ms-settings:appsfeatures", "notifications": "ms-settings:notifications",
    "personalization": "ms-settings:personalization", "background": "ms-settings:personalization-background",
    "privacy": "ms-settings:privacy", "storage": "ms-settings:storagesense", "about": "ms-settings:about",
    "mouse": "ms-settings:mousetouchpad", "keyboard": "ms-settings:typing", "power": "ms-settings:powersleep",
    "network": "ms-settings:network-status", "vpn": "ms-settings:network-vpn", "date": "ms-settings:dateandtime",
    "language": "ms-settings:regionlanguage", "default_apps": "ms-settings:defaultapps",
    "night_light": "ms-settings:nightlight", "focus": "ms-settings:quiethours", "home": "ms-settings:",
}


@tool("open_settings", "Open a Windows Settings page.",
      {"page": E("which page", sorted(SETTINGS_PAGES))}, ["page"])
def open_settings(page: str):
    os.startfile(SETTINGS_PAGES.get(page, "ms-settings:"))
    return f"opened {page} settings"


@tool("set_theme", "Switch Windows between dark and light mode.",
      {"mode": E("theme", ["dark", "light"])}, ["mode"])
def set_theme(mode: str):
    import winreg

    value = 0 if mode == "dark" else 1
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, "AppsUseLightTheme", 0, winreg.REG_DWORD, value)
        winreg.SetValueEx(key, "SystemUsesLightTheme", 0, winreg.REG_DWORD, value)
    # tell open windows the setting changed
    ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "ImmersiveColorSet", 0x0002, 3000, None)
    return f"{mode} mode on"


@tool("set_wallpaper", "Set the desktop wallpaper to an image file.", {"path": S("image file path")}, ["path"])
def set_wallpaper(path: str):
    from ..safety.paths import resolve

    p = resolve(path)
    if not p.exists():
        return f"file not found: {p}"
    ctypes.windll.user32.SystemParametersInfoW(20, 0, str(p), 3)
    return f"wallpaper set to {p.name}"


@tool("empty_recycle_bin", "Permanently empty the Recycle Bin.", level=CONFIRM,
      describe=lambda a: "Permanently empty the Recycle Bin")
def empty_recycle_bin():
    # flags: no confirmation, no progress UI, no sound
    ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x1 | 0x2 | 0x4)
    return "recycle bin emptied"


# ---------------------------------------------------------------- info


@tool("get_datetime", "Get the current local date, time and day of week.")
def get_datetime():
    now = dt.datetime.now().astimezone()
    return now.strftime("%A, %d %B %Y, %I:%M %p (%Z)")


@tool("system_info", "CPU, RAM, disk, battery, uptime, OS and network overview of this PC.")
def system_info():
    vm = psutil.virtual_memory()
    disks = []
    for part in psutil.disk_partitions(all=False):
        try:
            u = psutil.disk_usage(part.mountpoint)
            disks.append(f"{part.device} {u.free // 2**30}GB free of {u.total // 2**30}GB")
        except Exception:
            continue
    bat = psutil.sensors_battery()
    boot = dt.datetime.fromtimestamp(psutil.boot_time())
    return {
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "machine": platform.node(),
        "cpu_percent": psutil.cpu_percent(interval=0.5),
        "cpu_cores": psutil.cpu_count(),
        "ram": f"{vm.used // 2**20}MB used of {vm.total // 2**20}MB ({vm.percent}%)",
        "disks": disks,
        "battery": None if not bat else {"percent": bat.percent, "plugged_in": bat.power_plugged,
                                         "minutes_left": None if bat.secsleft < 0 else bat.secsleft // 60},
        "uptime_hours": round((dt.datetime.now() - boot).total_seconds() / 3600, 1),
    }


@tool("battery_status", "Battery percentage and whether charging.")
def battery_status():
    bat = psutil.sensors_battery()
    if not bat:
        return "no battery (desktop PC)"
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


@tool("kill_process", "Force-stop a process by name or PID (unsaved work is lost).",
      {"name_or_pid": S("process name like 'chrome.exe' or a PID")}, ["name_or_pid"],
      level=CONFIRM, describe=lambda a: f"Force-stop process {a.get('name_or_pid')}")
def kill_process(name_or_pid: str):
    target = str(name_or_pid).strip().lower()
    killed = []
    for p in psutil.process_iter(["pid", "name"]):
        name = (p.info["name"] or "").lower()
        if target.isdigit() and p.pid == int(target) or name in (target, target + ".exe"):
            if name in ("csrss.exe", "wininit.exe", "winlogon.exe", "lsass.exe", "services.exe", "smss.exe", "system"):
                raise PermissionError("refusing to kill a critical Windows process")
            try:
                p.kill()
                killed.append(f"{name}({p.pid})")
            except Exception as exc:
                killed.append(f"{name}({p.pid}) failed: {exc}")
    return ", ".join(killed) or "no matching process"


# ---------------------------------------------------------------- clipboard


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
