"""The agent loop: think → call tools (with safety checks) → observe → repeat → answer."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from ..context import ctx
from ..safety import audit
from ..safety.guard import decide
from ..tools.base import AUTO, BLOCKED, CONFIRM, REGISTRY
from .prompts import system_prompt

log = logging.getLogger(__name__)

MAX_STEPS = 14
MAX_TOOL_RESULT = 7000


@dataclass
class Hooks:
    """How the agent talks to the outside world (set up by core)."""

    on_text: Callable[[str], Awaitable[None]]
    on_tool_start: Callable[[str, str, dict[str, Any], str], Awaitable[None]]
    on_tool_end: Callable[[str, bool, str], Awaitable[None]]
    confirm: Callable[[str, str, dict[str, Any], str], Awaitable[bool]]


def _parse_args(raw: str) -> dict[str, Any]:
    if not raw or not raw.strip():
        return {}
    try:
        val = json.loads(raw)
        return val if isinstance(val, dict) else {}
    except json.JSONDecodeError:
        # some models wrap JSON in text; take the outermost {...}
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start: end + 1])
            except json.JSONDecodeError:
                pass
    return {}


def _short(result: str, limit: int = 160) -> str:
    one = " ".join(result.split())
    return one if len(one) <= limit else one[:limit] + "…"


async def _run_tool(name: str, args: dict[str, Any], hooks: Hooks) -> str:
    tool = REGISTRY.get(name)
    call_id = uuid.uuid4().hex[:10]
    if not tool:
        return f"ERROR: there is no tool named '{name}'."
    decision = decide(tool, args)
    level = decision.level
    await hooks.on_tool_start(call_id, name, args, level)

    if level == BLOCKED:
        msg = f"BLOCKED for safety: {decision.reason or 'this action is not allowed'}"
        audit.record(name, args, level, msg, False)
        await hooks.on_tool_end(call_id, False, msg)
        return msg

    if level == CONFIRM:
        description = tool.description_for(args)
        if ctx.settings["dry_run"]:
            msg = f"DRY RUN — would have done: {description}"
            audit.record(name, args, "dry_run", msg, True)
            await hooks.on_tool_end(call_id, True, msg)
            return msg
        approved = await hooks.confirm(call_id, name, args, description)
        if not approved:
            msg = "The user said NO — action cancelled. Don't retry it; acknowledge briefly."
            audit.record(name, args, level, "denied by user", False)
            await hooks.on_tool_end(call_id, False, "cancelled by you")
            return msg

    try:
        result = await tool.run(args)
        ok = not result.startswith(("ERROR", "BLOCKED"))
    except asyncio.CancelledError:
        audit.record(name, args, level, "cancelled (kill switch)", False)
        raise
    except PermissionError as exc:
        result, ok = f"BLOCKED for safety: {exc}", False
    except TypeError as exc:
        result, ok = f"ERROR: wrong arguments for {name}: {exc}", False
    except Exception as exc:  # noqa: BLE001
        log.exception("tool %s failed", name)
        result, ok = f"ERROR: {type(exc).__name__}: {exc}", False

    audit.record(name, args, level, result, ok)
    await hooks.on_tool_end(call_id, ok, _short(result))
    if len(result) > MAX_TOOL_RESULT:
        result = result[:MAX_TOOL_RESULT] + "\n…[truncated]"
    return result


async def run_agent(user_text: str, hooks: Hooks) -> str:
    """Run one user turn. Returns the final spoken reply text."""
    store = ctx.store
    history = store.recent_messages(limit=16)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt(ctx.settings, store.facts_for_prompt(user_text))}
    ]
    for m in history:
        if m["role"] in ("user", "assistant"):
            messages.append({"role": m["role"], "content": m["text"]})
    messages.append({"role": "user", "content": user_text})
    store.add_message("user", user_text)

    tools = [t.schema() for t in REGISTRY.values()]
    spoken: list[str] = []

    for step in range(MAX_STEPS):
        text, calls = await ctx.llm.chat(messages, tools, hooks.on_text)
        if text.strip():
            spoken.append(text.strip())
        if not calls:
            break
        messages.append({
            "role": "assistant",
            "content": text or None,
            "tool_calls": [
                {"id": c["id"] or f"call_{step}_{i}", "type": "function",
                 "function": {"name": c["name"], "arguments": c["arguments"] or "{}"}}
                for i, c in enumerate(calls)
            ],
        })
        for i, c in enumerate(calls):
            result = await _run_tool(c["name"], _parse_args(c["arguments"]), hooks)
            messages.append({"role": "tool", "tool_call_id": c["id"] or f"call_{step}_{i}", "content": result})
    else:
        # ran out of steps: ask for a final wrap-up without tools
        text, _ = await ctx.llm.chat(
            messages + [{"role": "user", "content": "(Stop using tools now and tell me briefly where things stand.)"}],
            None, hooks.on_text)
        spoken.append(text.strip())

    reply = " ".join(s for s in spoken if s).strip()
    store.add_message("assistant", reply)
    return reply
