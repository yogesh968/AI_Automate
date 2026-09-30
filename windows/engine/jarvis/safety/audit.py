"""Audit trail: every tool call is written to SQLite and to a JSONL file."""

import json
import time
from typing import Any

from ..context import ctx
from ..paths import logs_dir


def record(tool: str, args: dict[str, Any], level: str, result: str, ok: bool) -> None:
    ctx.store.add_audit(tool, args, level, result, ok)
    line = {"ts": time.time(), "tool": tool, "args": args, "level": level, "ok": ok, "result": result[:2000]}
    with open(logs_dir() / "audit.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")
