"""Long-term memory: things Jarvis should remember about the user."""

from __future__ import annotations

from ..context import ctx
from .base import I, S, tool


@tool("remember", "Save a lasting fact about the user or their world (preferences, people, projects, "
      "routines, 'my usual work setup is…'). Save proactively when the user shares something useful.",
      {"fact": S("one short self-contained fact, e.g. 'User's sister is Priya, phone +91…'")}, ["fact"])
def remember(fact: str):
    fid = ctx.store.add_fact(fact)
    return f"remembered (#{fid})"


@tool("recall", "Search long-term memory for facts about something.", {"query": S("what to look up")}, ["query"])
def recall(query: str):
    return ctx.store.search_facts(query, limit=10) or "nothing remembered about that"


@tool("list_memories", "List everything remembered (newest first).", {"limit": I("default 50")})
def list_memories(limit: int = 50):
    return ctx.store.all_facts(limit=int(limit)) or "memory is empty"


@tool("forget", "Delete a remembered fact by its id (from recall/list_memories).", {"fact_id": I("fact id")},
      ["fact_id"])
def forget(fact_id: int):
    return "forgotten" if ctx.store.delete_fact(int(fact_id)) else "no such memory"
