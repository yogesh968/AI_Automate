"""Routines: named lists of instructions, e.g. 'good morning' or 'work mode'."""

from __future__ import annotations

import json

from ..context import ctx
from ..paths import data_file
from .base import S, tool

DEFAULT_ROUTINES = {
    "good morning": "Greet the user warmly by time of day. Tell today's date, the weather, today's calendar events "
                    "(skip if Google isn't connected), pending reminders, and 3 top news headlines. Keep it short.",
    "work mode": "Open VS Code, open Chrome, set volume to 20, and turn on dark mode.",
    "good night": "Tell tomorrow's first calendar event if any, set volume to 10, and ask if I should lock the PC.",
}


def _load() -> dict[str, str]:
    path = data_file("routines.json")
    if not path.exists():
        path.write_text(json.dumps(DEFAULT_ROUTINES, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(DEFAULT_ROUTINES)


def _save(data: dict[str, str]) -> None:
    data_file("routines.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


@tool("list_routines", "List saved routines and what each does.")
def list_routines():
    return _load()


@tool("save_routine", "Create or update a routine (a named set of instructions to run later).",
      {"name": S("routine name, e.g. 'study mode'"), "instructions": S("what to do, step by step")},
      ["name", "instructions"])
def save_routine(name: str, instructions: str):
    data = _load()
    data[name.strip().lower()] = instructions.strip()
    _save(data)
    return f"routine '{name}' saved"


@tool("delete_routine", "Delete a routine.", {"name": S("routine name")}, ["name"])
def delete_routine(name: str):
    data = _load()
    if data.pop(name.strip().lower(), None) is None:
        return "no such routine"
    _save(data)
    return "deleted"


@tool("get_routine", "Get the instructions of a routine so you can carry them out now, step by step with tools.",
      {"name": S("routine name")}, ["name"])
def get_routine(name: str):
    data = _load()
    key = name.strip().lower()
    if key not in data:
        match = next((k for k in data if key in k or k in key), None)
        if not match:
            return f"no routine called '{name}'. Available: {', '.join(data)}"
        key = match
    return f"Routine '{key}': {data[key]}\nNow carry these steps out using your tools."
