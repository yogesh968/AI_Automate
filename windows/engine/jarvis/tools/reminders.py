"""Reminders and timers (stored in SQLite, fired by the core's scheduler loop)."""

from __future__ import annotations

import datetime as dt
import time

from ..context import ctx
from .base import E, I, N, S, tool


def _fmt(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts).strftime("%a %d %b, %I:%M %p")


@tool("set_reminder", "Set a reminder. Give either `at` (local ISO datetime) or `in_minutes`.",
      {"text": S("what to remind about"), "at": S("local ISO datetime like 2026-10-01T18:00"),
       "in_minutes": N("minutes from now"), "repeat": E("repeat", ["", "hourly", "daily", "weekly"])},
      ["text"])
def set_reminder(text: str, at: str = "", in_minutes: float = 0, repeat: str = ""):
    if at:
        when = dt.datetime.fromisoformat(at)
        if when.tzinfo is not None:
            when = when.astimezone().replace(tzinfo=None)
        due = when.timestamp()
    elif in_minutes:
        due = time.time() + float(in_minutes) * 60
    else:
        return "need a time: give `at` or `in_minutes`"
    if due < time.time() - 60 and not repeat:
        return "that time is already in the past"
    rid = ctx.store.add_reminder(text, due, repeat or "")
    return f"reminder #{rid} set for {_fmt(due)}" + (f", repeating {repeat}" if repeat else "")


@tool("set_timer", "Start a countdown timer.", {"minutes": N("length in minutes (0.5 = 30 seconds)"),
                                                "label": S("optional label")}, ["minutes"])
def set_timer(minutes: float, label: str = ""):
    due = time.time() + float(minutes) * 60
    rid = ctx.store.add_reminder(f"⏰ Timer: {label}" if label else "⏰ Timer done", due)
    return f"timer #{rid} set for {minutes:g} min (ends {_fmt(due)})"


@tool("list_reminders", "List upcoming reminders and timers.")
def list_reminders():
    rows = ctx.store.pending_reminders()
    return [{"id": r["id"], "text": r["text"], "when": _fmt(r["due"]), "repeat": r["repeat"]} for r in rows] \
        or "no reminders"


@tool("cancel_reminder", "Cancel a reminder or timer by id.", {"reminder_id": I("id")}, ["reminder_id"])
def cancel_reminder(reminder_id: int):
    return "cancelled" if ctx.store.cancel_reminder(int(reminder_id)) else "no such reminder"
