"""Live system telemetry for the HUD, and the rules for speaking up on its own (proactive alerts)."""

from __future__ import annotations

import datetime as dt
import logging
import socket
import time
from dataclasses import dataclass, field
from typing import Any

import psutil

log = logging.getLogger(__name__)


class Telemetry:
    """Cheap, non-blocking snapshots of CPU / RAM / disk / battery / network."""

    def __init__(self) -> None:
        # Own CPU-time baseline: psutil.cpu_percent(None) keeps one global baseline that any other caller resets.
        self._cpu_times = psutil.cpu_times()
        self._cpu_last = 0.0
        self._net = psutil.net_io_counters()
        self._net_t = time.monotonic()
        self._procs: dict[int, psutil.Process] = {}
        self._procs_t = 0.0
        self._top: list[dict[str, Any]] = []
        self._top_primed = False
        self.online: bool | None = None
        self._online_t = 0.0

    def _cpu_percent(self) -> float:
        cur = psutil.cpu_times()
        prev, self._cpu_times = self._cpu_times, cur
        total = sum(cur) - sum(prev)
        if total <= 0:
            return self._cpu_last
        idle = (cur.idle - prev.idle) + (getattr(cur, "iowait", 0) - getattr(prev, "iowait", 0))
        self._cpu_last = round(max(0.0, min(100.0, 100.0 * (1 - idle / total))), 1)
        return self._cpu_last

    def _top_processes(self, count: int = 5) -> list[dict[str, Any]]:
        # Refresh every ~4 s; per-process cpu_percent needs two samples, so keep Process objects around.
        now = time.monotonic()
        if now - self._procs_t < 4 and self._top:
            return self._top
        self._procs_t = now
        seen: dict[int, psutil.Process] = {}
        rows = []
        cores = psutil.cpu_count() or 1
        for p in psutil.process_iter(["name", "memory_info"]):
            proc = self._procs.get(p.pid, p)
            seen[p.pid] = proc
            try:
                cpu = proc.cpu_percent(None) / cores
                name = p.info["name"] or "?"
                if p.pid == 0 or name.lower() in ("system idle process", "idle"):
                    continue
                rows.append({"name": name, "cpu": round(cpu, 1),
                             "mem_mb": round((p.info["memory_info"].rss if p.info["memory_info"] else 0) / 2**20)})
            except psutil.Error:
                continue
        self._procs = seen
        if not self._top_primed:
            # the first pass only sets each process's baseline; every value would read 0 %
            self._top_primed = True
            self._procs_t = now - 2.5  # take the real sample ~1.5 s from now
            return []
        rows.sort(key=lambda r: (r["cpu"], r["mem_mb"]), reverse=True)
        self._top = rows[:count]
        return self._top

    def check_online(self) -> bool:
        """TCP connect to public DNS servers — no data sent. Cached for 20 s."""
        now = time.monotonic()
        if self.online is not None and now - self._online_t < 20:
            return self.online
        self._online_t = now
        ok = False
        for host in ("1.1.1.1", "8.8.8.8"):
            try:
                with socket.create_connection((host, 53), timeout=2):
                    ok = True
                    break
            except OSError:
                continue
        self.online = ok
        return ok

    @staticmethod
    def battery() -> dict[str, Any] | None:
        bat = psutil.sensors_battery()
        if not bat:
            return None
        return {"percent": round(bat.percent), "plugged": bool(bat.power_plugged),
                "minutes_left": None if bat.secsleft is None or bat.secsleft < 0 else int(bat.secsleft // 60)}

    def snapshot(self, with_processes: bool = True) -> dict[str, Any]:
        vm = psutil.virtual_memory()
        try:
            disk = psutil.disk_usage(str(_system_drive()))
            disk_pct = disk.percent
            disk_free = round(disk.free / 2**30)
        except Exception:
            disk_pct, disk_free = None, None
        net = psutil.net_io_counters()
        now = time.monotonic()
        span = max(0.001, now - self._net_t)
        up = (net.bytes_sent - self._net.bytes_sent) / span
        down = (net.bytes_recv - self._net.bytes_recv) / span
        self._net, self._net_t = net, now
        try:
            freq = psutil.cpu_freq()
            ghz = round(freq.current / 1000, 2) if freq else None
        except Exception:
            ghz = None
        return {
            "ts": time.time(),
            "cpu": self._cpu_percent(),
            "cpu_ghz": ghz,
            "cores": psutil.cpu_count(),
            "ram": vm.percent,
            "ram_used_gb": round(vm.used / 2**30, 1),
            "ram_total_gb": round(vm.total / 2**30, 1),
            "disk": disk_pct,
            "disk_free_gb": disk_free,
            "battery": self.battery(),
            "net_up_kbps": round(max(0.0, up) / 1024, 1),
            "net_down_kbps": round(max(0.0, down) / 1024, 1),
            "online": self.online,
            "uptime_s": int(time.time() - psutil.boot_time()),
            "processes": len(psutil.pids()),
            "top": self._top_processes() if with_processes else [],
        }


def _system_drive():
    import os
    from pathlib import Path

    return Path(os.environ.get("SystemDrive", "C:") + "\\") if os.name == "nt" else Path("/")


# --------------------------------------------------------------------------- proactive alerts

@dataclass
class Alert:
    key: str
    title: str
    # (english, hinglish) — core picks per persona/language
    en: str
    hi: str
    kind: str = "warning"


@dataclass
class AlertRules:
    """Turns a stream of snapshots into a few well-timed alerts (never spammy).

    Pure logic: feed() takes a snapshot dict and the current time, returns alerts to announce.
    """

    cpu_high: float = 92.0
    cpu_high_secs: float = 90.0
    ram_high: float = 93.0
    disk_high: float = 95.0
    disk_cooldown: float = 6 * 3600
    cooldown: float = 15 * 60
    _last: dict[str, float] = field(default_factory=dict)
    _cpu_since: float | None = None
    _ram_since: float | None = None
    _bat_warned: set[int] = field(default_factory=set)
    _full_warned: bool = False
    _was_online: bool | None = None
    _offline_count: int = 0

    def _ready(self, key: str, now: float) -> bool:
        return now - self._last.get(key, -1e12) >= self.cooldown

    def _fire(self, key: str, now: float) -> None:
        self._last[key] = now

    def feed(self, s: dict[str, Any], now: float) -> list[Alert]:
        out: list[Alert] = []

        # ---- battery: warn once at 20 %, 10 %, 5 % while discharging; once when full on charger
        bat = s.get("battery")
        if bat:
            pct, plugged = bat["percent"], bat["plugged"]
            if plugged:
                self._bat_warned.clear()
                if pct >= 100 and not self._full_warned:
                    self._full_warned = True
                    out.append(Alert("battery_full", "Battery full",
                                     "Battery is fully charged. You can unplug the charger.",
                                     "Battery full charge ho gayi hai, charger nikal sakte ho.", "info"))
                if pct < 95:
                    self._full_warned = False
            else:
                self._full_warned = False
                for level in (5, 10, 20):
                    if pct <= level and level not in self._bat_warned:
                        self._bat_warned.update(x for x in (5, 10, 20) if x >= level)
                        mins = bat.get("minutes_left")
                        left_en = f" About {mins} minutes left." if mins else ""
                        left_hi = f" Lagbhag {mins} minute bache hain." if mins else ""
                        out.append(Alert("battery_low", "Battery low",
                                         f"Battery at {pct} percent.{left_en} I'd suggest plugging in.",
                                         f"Battery {pct} percent pe hai.{left_hi} Charger laga lo.",
                                         "warning"))
                        break

        # ---- CPU sustained overload
        cpu = s.get("cpu") or 0
        if cpu >= self.cpu_high:
            if self._cpu_since is None:
                self._cpu_since = now
            if now - self._cpu_since >= self.cpu_high_secs and self._ready("cpu", now):
                self._fire("cpu", now)
                top = (s.get("top") or [{}])[0].get("name", "")
                who_en = f" {top} is the heaviest process." if top else ""
                who_hi = f" Sabse zyada {top} use kar raha hai." if top else ""
                out.append(Alert("cpu", "CPU overload",
                                 f"CPU has been above {int(self.cpu_high)} percent for a while.{who_en}",
                                 f"CPU kaafi der se {int(self.cpu_high)} percent se upar hai.{who_hi}"))
        else:
            self._cpu_since = None

        # ---- RAM pressure (sustained 30 s)
        ram = s.get("ram") or 0
        if ram >= self.ram_high:
            if self._ram_since is None:
                self._ram_since = now
            if now - self._ram_since >= 30 and self._ready("ram", now):
                self._fire("ram", now)
                out.append(Alert("ram", "Memory almost full",
                                 f"Memory is at {int(ram)} percent. Closing a few apps would help.",
                                 f"RAM {int(ram)} percent bhar gayi hai, kuch apps band kar do."))
        else:
            self._ram_since = None

        # ---- system drive almost full (rarely: every few hours at most)
        disk = s.get("disk")
        if disk is not None and disk >= self.disk_high and now - self._last.get("disk", -1e12) >= self.disk_cooldown:
            self._fire("disk", now)
            free = s.get("disk_free_gb")
            free_en = f" Only {free} gigabytes left." if free is not None else ""
            free_hi = f" Sirf {free} GB bacha hai." if free is not None else ""
            out.append(Alert("disk", "Disk almost full",
                             f"The system drive is {int(disk)} percent full.{free_en} Shall I find what's taking the space?",
                             f"Disk {int(disk)} percent full ho gayi hai.{free_hi} Bolo to main dekh loon kya jagah le raha hai?"))

        # ---- internet: announce a drop only after 2 failed checks, and the recovery
        online = s.get("online")
        if online is not None:
            if online:
                if self._was_online is False and self._offline_count >= 2:
                    out.append(Alert("net_up", "Back online", "We're back online.",
                                     "Internet wapas aa gaya.", "info"))
                self._offline_count = 0
                self._was_online = True
            else:
                self._offline_count += 1
                if self._offline_count == 2 and self._was_online:
                    out.append(Alert("net_down", "Internet down",
                                     "We've lost the internet connection. Voice recognition won't work until it's back.",
                                     "Internet chala gaya hai. Jab tak wapas nahi aata, voice commands kaam nahi karenge."))
                    self._was_online = False
        return out


# --------------------------------------------------------------------------- greeting

def part_of_day(hour: int) -> str:
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 22:
        return "evening"
    return "night"


def greeting(persona: str, address: str, user: str, script: str, snapshot: dict[str, Any] | None,
             now: dt.datetime | None = None) -> str:
    """The line spoken when JARVIS boots. No LLM needed, so it works before any API key is set."""
    now = now or dt.datetime.now()
    pod = part_of_day(now.hour)
    who = address or user or "sir"
    t = now.strftime("%I:%M %p").lstrip("0")
    extra_en = extra_hi = ""
    bat = (snapshot or {}).get("battery")
    if bat and not bat["plugged"] and bat["percent"] <= 25:
        extra_en = f" Battery is at {bat['percent']} percent, by the way."
        extra_hi = f" Battery {bat['percent']} percent pe hai, dhyan rakhna."
    if persona == "classic":
        if pod == "night":
            return f"Working late, {who}? It's {t}. All systems are online.{extra_en}"
        return f"Good {pod}, {who}. It's {t}. All systems are online and ready.{extra_en}"
    hello = {"morning": "Good morning", "afternoon": "Good afternoon", "evening": "Good evening",
             "night": "Itni raat ko jag rahe ho"}[pod]
    name = user or "boss"
    if script == "devanagari":
        base = (f"{hello} {name}, सारे systems online हैं।" if pod != "night"
                else f"इतनी रात को भी जाग रहे हो {name}? सारे systems online हैं।")
    else:
        base = f"{hello} {name}, saare systems online hain." if pod != "night" else \
            f"{hello} {name}? Saare systems online hain."
    return base + extra_hi
