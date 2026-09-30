"""Shared runtime objects that tools can reach without passing them around."""

from __future__ import annotations

from typing import TYPE_CHECKING, Awaitable, Callable

if TYPE_CHECKING:
    from .brain.llm import LLM
    from .config import Settings
    from .memory.store import Store


class Context:
    settings: "Settings"
    store: "Store"
    llm: "LLM"
    # async fn(title, body, kind) -> None ; set by core
    notify: Callable[[str, str, str], Awaitable[None]]


ctx = Context()
