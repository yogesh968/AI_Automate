"""Auto-memory: after a conversation turn, quietly pick out lasting facts about the user and remember them."""

from __future__ import annotations

import json
import logging
import re

from ..context import ctx

log = logging.getLogger(__name__)

EXTRACT_PROMPT = """You maintain the long-term memory of a personal assistant.
From the exchange below, extract ONLY durable facts about the user that will still be true and useful weeks from now:
their name, family and friends, job, projects, preferences, habits, important dates, places, devices, accounts they use.

Do NOT extract: one-off requests or commands ("open chrome", "set volume"), questions, small talk, the current time,
anything about the assistant itself, or facts already in KNOWN.

Write each fact as one short self-contained sentence in English, about "User" (e.g. "User's sister is Priya.",
"User prefers dark mode.", "User works at Futeservices as a web developer.").
Answer with a JSON array of strings and nothing else. Usually the right answer is [].

KNOWN:
{known}

EXCHANGE:
User: {user}
Assistant: {assistant}"""

_WORD = re.compile(r"\w+", re.UNICODE)
_SKIP = re.compile(r"^\s*(open|close|play|stop|pause|set|turn|mute|volume|search|kholo|band|chalao|bajao)\b", re.I)


def _tokens(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text) if len(w) > 2}


def is_duplicate(fact: str, known: list[str]) -> bool:
    new = _tokens(fact)
    if not new:
        return True
    for k in known:
        old = _tokens(k)
        if not old:
            continue
        overlap = len(new & old) / len(new | old)
        if overlap >= 0.6 or new <= old:
            return True
    return False


def worth_checking(user_text: str) -> bool:
    """Skip the LLM call for plain commands — most turns contain nothing worth remembering."""
    words = _WORD.findall(user_text)
    if len(words) < 4:
        return False
    if _SKIP.match(user_text) and len(words) < 10:
        return False
    return True


def parse_facts(raw: str) -> list[str]:
    start, end = raw.find("["), raw.rfind("]")
    if start < 0 or end <= start:
        return []
    try:
        data = json.loads(raw[start: end + 1])
    except json.JSONDecodeError:
        return []
    out = []
    for item in data if isinstance(data, list) else []:
        if isinstance(item, str) and 6 <= len(item.strip()) <= 200:
            out.append(item.strip())
    return out[:3]


async def learn_from_turn(user_text: str, reply: str) -> list[str]:
    """Returns the facts that were newly saved."""
    if not ctx.settings["auto_memory"] or not worth_checking(user_text):
        return []
    known = [f["text"] for f in ctx.store.all_facts(limit=80)]
    prompt = EXTRACT_PROMPT.format(known="\n".join(f"- {k}" for k in known[:60]) or "(none)",
                                   user=user_text[:1500], assistant=reply[:800])
    try:
        raw = await ctx.llm.complete(prompt)
    except Exception as exc:  # noqa: BLE001 — memory is best-effort, never break a turn
        log.debug("auto-memory skipped: %s", exc)
        return []
    saved = []
    for fact in parse_facts(raw):
        if not is_duplicate(fact, known + saved):
            ctx.store.add_fact(fact)
            saved.append(fact)
            log.info("auto-memory: %s", fact)
    return saved
