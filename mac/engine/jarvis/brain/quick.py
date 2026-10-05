"""Instant commands: everyday one-liners ("chrome kholo", "volume 30", "pause") run straight away,
without a round-trip to the language model. Anything that doesn't match exactly goes to the LLM as usual.
"""

from __future__ import annotations

import datetime as dt
import random
import re
from dataclasses import dataclass
from typing import Any, Callable

_LEAD = re.compile(r"^\s*(?:(?:hey|hi|ok|okay|oye|arre|are)\s+)?(?:jarvis|जार्विस)?[\s,!.]*", re.I)
_POLITE = re.compile(r"\b(?:please|plz|pls|zara|jaldi|abhi|na|yaar|bhai)\b", re.I)
_TAIL = re.compile(r"[\s,!.?।]+$")

# Hinglish markers: reply in Hindi when the user spoke Hindi
_HINDI = re.compile(r"\b(?:karo|kar|do|kholo|khol|band|bandh|kam|zyada|jyada|badhao|badha|ghatao|kya|hai|hain|"
                    r"kitne|kitna|baje|chalao|chala|laga|lagao|roko|ruko|agla|agle|pichla|gaana|gana|dikhao|"
                    r"hatao|samay|abhi)\b|[ऀ-ॿ]", re.I)

# things that sound like apps but need other tools (websites, folders, …) — leave them to the LLM
_NOT_APPS = re.compile(r"\b(?:youtube|google|gmail|facebook|instagram|twitter|linkedin|netflix|website|site|page|"
                       r"folder|file|files|downloads|documents|desktop|tab|link|hud|screen|song|gaana|video|"
                       r"email|mail\s+\w+|whatsapp\s+\w+|and|aur|then|phir|this|that|it|window|windows|yeh|ye|"
                       r"isko|sab|all|everything)\b|[./:]", re.I)

_APP = r"([a-z0-9][a-z0-9 +&'-]{0,30}?)"
_OPEN = [re.compile(rf"^(?:open|launch)\s+(?:the\s+)?{_APP}(?:\s+app)?$", re.I),
         re.compile(rf"^{_APP}(?:\s+app)?\s+(?:kholo|khol\s+do|khol|open\s+karo|open\s+kar\s+do|open\s+karna|"
                    r"open|chalu\s+karo|chalu\s+kar\s+do|start\s+karo|start\s+kar\s+do|launch\s+karo)$", re.I)]
_CLOSE = [re.compile(rf"^(?:close|quit|exit)\s+(?:the\s+)?{_APP}(?:\s+app)?$", re.I),
          re.compile(rf"^{_APP}(?:\s+app)?\s+(?:band\s+karo|band\s+kar\s+do|bandh\s+karo|bandh\s+kar\s+do|"
                     r"close\s+karo|close\s+kar\s+do|close|quit\s+karo)$", re.I)]

_VOL_SET = re.compile(r"^(?:set\s+)?(?:the\s+)?(?:volume|awaaz|awaz|आवाज़|आवाज)\s+(?:to\s+|ko\s+|at\s+)?(\d{1,3})"
                      r"(?:\s*(?:%|percent|pe|par|kar\s+do|karo|kardo))*$", re.I)
_VOL_UP = re.compile(r"^(?:(?:volume|awaaz|awaz|sound)\s+(?:up|badhao|badha\s+do|zyada\s+karo|jyada\s+karo|"
                     r"tez\s+karo|increase\s+karo|increase|louder|thoda\s+badhao)|(?:increase|raise|turn\s+up)\s+"
                     r"(?:the\s+)?volume)$", re.I)
_VOL_DOWN = re.compile(r"^(?:(?:volume|awaaz|awaz|sound)\s+(?:down|kam\s+karo|kam\s+kar\s+do|ghatao|ghata\s+do|"
                       r"decrease\s+karo|decrease|lower|thoda\s+kam\s+karo|dheere\s+karo)|(?:decrease|lower|"
                       r"turn\s+down)\s+(?:the\s+)?volume)$", re.I)
_MUTE = re.compile(r"^(?:mute|mute\s+karo|mute\s+kar\s+do|(?:sound|awaaz|awaz|volume)\s+(?:band\s+karo|"
                   r"band\s+kar\s+do|mute\s+karo|off|off\s+karo))$", re.I)
_UNMUTE = re.compile(r"^(?:unmute|unmute\s+karo|unmute\s+kar\s+do|(?:sound|awaaz|awaz|volume)\s+(?:on|on\s+karo|"
                     r"chalu\s+karo))$", re.I)

_MEDIA = [
    (re.compile(r"^(?:pause|pause\s+karo|pause\s+kar\s+do|(?:music|gaana|gana|song|video)\s+(?:pause|roko|"
                r"band\s+karo|pause\s+karo|stop\s+karo)|play|resume|resume\s+karo|play\s+karo|"
                r"(?:music|gaana|gana|song)\s+(?:chalao|play\s+karo|resume\s+karo))$", re.I), "play_pause"),
    (re.compile(r"^(?:next|next\s+song|next\s+track|skip|skip\s+karo|agla\s+(?:gaana|gana|song)|next\s+(?:gaana|gana)"
                r"(?:\s+(?:chalao|lagao|karo))?|agla\s+(?:gaana|gana|song)\s+(?:chalao|lagao))$", re.I), "next"),
    (re.compile(r"^(?:previous|previous\s+song|previous\s+track|pichla\s+(?:gaana|gana|song)(?:\s+(?:chalao|lagao))?)$",
                re.I), "previous"),
]

_TIME = re.compile(r"^(?:what(?:'s|\s+is)\s+the\s+time|what\s+time\s+is\s+it|time\s+kya\s+(?:hai|hua|ho\s+gaya)|"
                   r"kitne\s+baje\s+(?:hain|hai|gaye)|kya\s+time\s+(?:hai|hua)|time\s+batao|samay\s+kya\s+hai|"
                   r"टाइम\s+क्या\s+(?:है|हुआ)|कितने\s+बजे\s+(?:हैं|है))$", re.I)
_BATTERY = re.compile(r"^(?:battery|battery\s+(?:kitni\s+hai|kitna\s+hai|status|level|percentage|kitni\s+bachi\s+hai)|"
                      r"how\s+much\s+battery(?:\s+is\s+left)?|what(?:'s|\s+is)\s+the\s+battery(?:\s+level)?)$", re.I)
_LOCK = re.compile(r"^(?:lock(?:\s+the)?(?:\s+(?:screen|mac|computer|laptop))?|(?:screen|mac|laptop)\s+lock\s+"
                   r"(?:karo|kar\s+do)|lock\s+karo|lock\s+kar\s+do)$", re.I)
_HUD_ON = re.compile(r"^(?:show(?:\s+the)?\s+hud|hud\s+(?:dikhao|kholo|on|on\s+karo)|open\s+hud)$", re.I)
_HUD_OFF = re.compile(r"^(?:hide(?:\s+the)?\s+hud|close(?:\s+the)?\s+hud|hud\s+(?:band\s+karo|hatao|off|"
                      r"off\s+karo|chhota\s+karo))$", re.I)


@dataclass
class Quick:
    tool: str
    args: dict[str, Any]
    hindi: bool
    reply: Callable[[str, "Voice"], str]  # (tool result, voice) -> spoken line


class Voice:
    """Short replies in the selected persona and script."""

    def __init__(self, settings, hindi: bool) -> None:
        self.classic = (settings["persona"] or "classic") == "classic"
        self.sir = (settings["address_as"] or "").strip() or settings["user_name"] or "sir"
        self.hindi = hindi
        self.deva = settings["hindi_script"] != "roman"

    def say(self, en: str, deva: str, roman: str) -> str:
        if self.hindi:
            return deva if self.deva else roman
        return en

    def done(self) -> str:
        if self.classic:
            return self.say(random.choice([f"Done, {self.sir}.", f"Right away, {self.sir}.", "Done."]),
                            f"जी {self.sir}, हो गया।", f"Ji {self.sir}, ho gaya.")
        return self.say(random.choice(["Done.", "Got it.", "Done, boss."]),
                        random.choice(["हो गया।", "हो गया boss।", "ठीक है, हो गया।"]),
                        random.choice(["Ho gaya.", "Ho gaya boss.", "Theek hai, ho gaya."]))


def _clean(text: str) -> str:
    text = _LEAD.sub("", text, count=1)
    text = _POLITE.sub(" ", text)
    text = _TAIL.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def _app_ok(name: str) -> bool:
    return bool(name) and len(name.split()) <= 3 and not _NOT_APPS.search(name)


def _opened(result: str, v: Voice) -> str:
    app = result.removeprefix("opened ").strip() or "it"
    if v.classic:
        return v.say(f"Opening {app}, {v.sir}.", f"जी {v.sir}, {app} खोल दिया।", f"Ji {v.sir}, {app} khol diya.")
    return v.say(f"{app} is open.", f"{app} खोल दिया।", f"{app} khol diya.")


def _closed(_result: str, v: Voice) -> str:
    return v.done()


def _time(_result: str, v: Voice) -> str:
    now = dt.datetime.now()
    clock = now.strftime("%I:%M %p").lstrip("0")
    if v.classic:
        return v.say(f"It's {clock}, {v.sir}.", f"{v.sir}, अभी {clock} हुए हैं।", f"{v.sir}, abhi {clock} hue hain.")
    return v.say(f"It's {clock}.", f"अभी {clock} हुए हैं।", f"Abhi {clock} hue hain.")


def _battery(result: str, v: Voice) -> str:
    m = re.match(r"(\d+)%( charging)?(?:, about (\d+) minutes left)?", result)
    if not m:
        return v.say(f"No battery on this Mac, {v.sir}.", "इस Mac में battery नहीं है।", "Is Mac mein battery nahi hai.")
    pct, charging, mins = m.group(1), bool(m.group(2)), m.group(3)
    en = f"Battery at {pct} percent" + (", charging" if charging else "") + \
         (f", about {mins} minutes left" if mins and not charging else "") + (f", {v.sir}." if v.classic else ".")
    deva = f"Battery {pct} percent है" + (", charge हो रही है" if charging else "") + "।"
    roman = f"Battery {pct} percent hai" + (", charge ho rahi hai" if charging else "") + "."
    return v.say(en, deva, roman)


def match(text: str) -> Quick | None:
    """Returns the instant command for this utterance, or None to let the LLM handle it."""
    raw = text.strip()
    if not raw or len(raw) > 80:
        return None
    hindi = bool(_HINDI.search(raw))
    t = _clean(raw)
    if not t:
        return None

    done = lambda _r, v: v.done()  # noqa: E731

    for pat in _OPEN:
        m = pat.match(t)
        if m and _app_ok(m.group(1)):
            return Quick("open_app", {"name": m.group(1).strip()}, hindi, _opened)
    for pat in _CLOSE:
        m = pat.match(t)
        if m and _app_ok(m.group(1)):
            return Quick("close_app", {"name": m.group(1).strip()}, hindi, _closed)

    m = _VOL_SET.match(t)
    if m and int(m.group(1)) <= 100:
        level = int(m.group(1))
        return Quick("set_volume", {"level": level}, hindi,
                     lambda _r, v: v.say(f"Volume at {level}.", f"Volume {level} कर दिया।", f"Volume {level} kar diya."))
    if _VOL_UP.match(t):
        return Quick("change_volume", {"delta": 10}, hindi, done)
    if _VOL_DOWN.match(t):
        return Quick("change_volume", {"delta": -10}, hindi, done)
    if _MUTE.match(t):
        return Quick("mute", {"muted": True}, hindi, lambda _r, v: "")  # silence is the point
    if _UNMUTE.match(t):
        return Quick("mute", {"muted": False}, hindi, done)
    for pat, action in _MEDIA:
        if pat.match(t):
            return Quick("media_control", {"action": action}, hindi, lambda _r, v: "")
    if _TIME.match(t):
        return Quick("get_datetime", {}, hindi, _time)
    if _BATTERY.match(t):
        return Quick("battery_status", {}, hindi, _battery)
    if _LOCK.match(t):
        return Quick("lock_screen", {}, hindi, lambda _r, v: "")
    if _HUD_ON.match(t):
        return Quick("show_hud", {}, hindi, done)
    if _HUD_OFF.match(t):
        return Quick("hide_hud", {}, hindi, done)
    return None


def failed(result: str) -> bool:
    """The tool couldn't do it — let the LLM take over (it has more tools to try)."""
    low = result.lower()
    return (result.startswith(("ERROR", "BLOCKED")) or "couldn't find" in low or "not installed" in low
            or "isn't running" in low)
