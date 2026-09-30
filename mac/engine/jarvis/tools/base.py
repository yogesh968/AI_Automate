"""Tool registry. Every ability Jarvis has is a function registered with @tool."""

from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import dataclass, field
from typing import Any, Callable

# Permission levels
AUTO = "auto"        # harmless / read-only: runs immediately
CONFIRM = "confirm"  # changes things: user must approve
BLOCKED = "blocked"  # never runs


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    func: Callable[..., Any]
    level: str | Callable[[dict[str, Any]], str] = AUTO
    describe: Callable[[dict[str, Any]], str] | None = None
    tags: list[str] = field(default_factory=list)

    def level_for(self, args: dict[str, Any]) -> str:
        return self.level(args) if callable(self.level) else self.level

    def description_for(self, args: dict[str, Any]) -> str:
        if self.describe:
            try:
                return self.describe(args)
            except Exception:
                pass
        pretty = ", ".join(f"{k}={v!r}" for k, v in args.items())
        return f"{self.name}({pretty})"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.parameters},
        }

    async def run(self, args: dict[str, Any]) -> str:
        if inspect.iscoroutinefunction(self.func):
            result = await self.func(**args)
        else:
            result = await asyncio.to_thread(self.func, **args)
        if result is None:
            return "done"
        if isinstance(result, str):
            return result
        return json.dumps(result, ensure_ascii=False, default=str)


REGISTRY: dict[str, Tool] = {}


def tool(
    name: str,
    description: str,
    params: dict[str, dict[str, Any]] | None = None,
    required: list[str] | None = None,
    level: str | Callable[[dict[str, Any]], str] = AUTO,
    describe: Callable[[dict[str, Any]], str] | None = None,
):
    """Register a function as a tool. `params` maps arg name -> JSON schema."""

    def wrap(func: Callable[..., Any]) -> Callable[..., Any]:
        REGISTRY[name] = Tool(
            name=name,
            description=description,
            parameters={
                "type": "object",
                "properties": params or {},
                "required": required or [],
            },
            func=func,
            level=level,
            describe=describe,
        )
        return func

    return wrap


def S(desc: str, **extra: Any) -> dict[str, Any]:
    return {"type": "string", "description": desc, **extra}


def I(desc: str, **extra: Any) -> dict[str, Any]:
    return {"type": "integer", "description": desc, **extra}


def N(desc: str, **extra: Any) -> dict[str, Any]:
    return {"type": "number", "description": desc, **extra}


def B(desc: str) -> dict[str, Any]:
    return {"type": "boolean", "description": desc}


def E(desc: str, options: list[str]) -> dict[str, Any]:
    return {"type": "string", "description": desc, "enum": options}


def ARR(desc: str, item_type: str = "string") -> dict[str, Any]:
    return {"type": "array", "description": desc, "items": {"type": item_type}}


def load_all() -> dict[str, Tool]:
    """Import every tool module so their @tool decorators run."""
    from . import (  # noqa: F401
        apps,
        browser,
        files,
        google_services,
        input_control,
        mac_apps,
        mac_ui,
        memory_tools,
        reminders,
        routines,
        screen,
        shell,
        system,
        web,
    )

    return REGISTRY
