"""Apple app integrations via AppleScript: Notes, Reminders, Calendar, Messages, Music, Finder, notifications.
First use of each app triggers a macOS 'Jarvis wants to control …' prompt (Automation permission)."""

from __future__ import annotations

import datetime as dt

from ..safety.paths import resolve
from ._mac import as_str, osa, run
from .base import CONFIRM, E, I, S, tool


def _as_date_lines(var: str, when: dt.datetime) -> str:
    """AppleScript lines that build a date locale-independently."""
    return (f"set {var} to current date\n"
            f"set day of {var} to 1\n"
            f"set year of {var} to {when.year}\n"
            f"set month of {var} to {when.month}\n"
            f"set day of {var} to {when.day}\n"
            f"set hours of {var} to {when.hour}\n"
            f"set minutes of {var} to {when.minute}\n"
            f"set seconds of {var} to 0\n")


def _parse(iso: str) -> dt.datetime:
    when = dt.datetime.fromisoformat(iso)
    if when.tzinfo is not None:
        when = when.astimezone().replace(tzinfo=None)
    return when


def _html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")


# ---------------------------------------------------------------- Notes


@tool("apple_notes_create", "Create a note in Apple Notes.",
      {"title": S("note title"), "body": S("note text"), "folder": S("optional folder name, default 'Notes'")},
      ["title", "body"])
def apple_notes_create(title: str, body: str, folder: str = ""):
    html = f"<h1>{_html(title)}</h1><div>{_html(body)}</div>"
    target = f"folder {as_str(folder)}" if folder else "default account"
    osa(f'tell application "Notes"\n'
        f"try\nmake new note at {target} with properties {{body:{as_str(html)}}}\n"
        f"on error\nmake new note with properties {{body:{as_str(html)}}}\nend try\nend tell")
    return f"note '{title}' created"


@tool("apple_notes_search", "Search Apple Notes and return matching notes with their text.",
      {"query": S("text to find"), "max_results": I("default 5")}, ["query"])
def apple_notes_search(query: str, max_results: int = 5):
    out = osa(f'tell application "Notes"\n'
              f"set found to (every note whose name contains {as_str(query)} or plaintext contains {as_str(query)})\n"
              f'set out to ""\nset n to 0\n'
              f"repeat with nt in found\n"
              f"set n to n + 1\nif n > {int(max_results)} then exit repeat\n"
              f"set t to plaintext of nt\n"
              f"if (length of t) > 1500 then set t to text 1 thru 1500 of t\n"
              f'set out to out & "### " & (name of nt) & linefeed & t & linefeed & linefeed\n'
              f"end repeat\nreturn out\nend tell", timeout=60)
    return out or "no matching notes"


# ---------------------------------------------------------------- Reminders app


@tool("apple_reminders_add", "Add a to-do to the Apple Reminders app (syncs to iPhone). For Jarvis's own spoken "
      "reminders use set_reminder instead.",
      {"text": S("the to-do"), "due": S("optional local ISO datetime"), "list": S("optional list name")},
      ["text"])
def apple_reminders_add(text: str, due: str = "", list: str = ""):
    props = f"name:{as_str(text)}"
    pre = ""
    if due:
        pre = _as_date_lines("d", _parse(due))
        props += ", due date:d, remind me date:d"
    where = f"list {as_str(list)}" if list else "default list"
    osa(f'{pre}tell application "Reminders"\n'
        f"make new reminder at end of {where} with properties {{{props}}}\nend tell")
    return f"added to Reminders: {text}" + (f" (due {due})" if due else "")


# ---------------------------------------------------------------- Calendar app


@tool("apple_calendar_list", "List upcoming events from the macOS Calendar app (includes iCloud/Google accounts "
      "added to macOS).", {"days": I("how many days ahead, default 1 (today)")})
def apple_calendar_list(days: int = 1):
    n = max(1, min(int(days), 31))
    out = osa(f"set startD to current date\nset time of startD to 0\n"
              f"set endD to startD + ({n} * days)\n"
              f'set out to ""\n'
              f'tell application "Calendar"\n'
              f"repeat with c in calendars\n"
              f"set evs to (every event of c whose start date ≥ startD and start date < endD)\n"
              f"repeat with e in evs\n"
              f'set out to out & (summary of e) & " | " & ((start date of e) as string) & " | " & (name of c) & linefeed\n'
              f"end repeat\nend repeat\nend tell\nreturn out", timeout=90)
    lines = sorted(ln for ln in out.splitlines() if ln.strip())
    return lines or "no events"


@tool("apple_calendar_add", "Create an event in the macOS Calendar app.",
      {"title": S("event title"), "start": S("local ISO datetime, e.g. 2026-10-01T17:00"),
       "duration_minutes": I("default 60"), "calendar": S("optional calendar name"),
       "location": S("optional"), "notes": S("optional")},
      ["title", "start"], level=CONFIRM,
      describe=lambda a: f"Add '{a.get('title')}' to Calendar at {a.get('start')}")
def apple_calendar_add(title: str, start: str, duration_minutes: int = 60, calendar: str = "",
                       location: str = "", notes: str = ""):
    begin = _parse(start)
    finish = begin + dt.timedelta(minutes=int(duration_minutes))
    cal = f"calendar {as_str(calendar)}" if calendar else "first calendar whose writable is true"
    osa(_as_date_lines("s", begin) + _as_date_lines("e", finish)
        + f'tell application "Calendar"\n'
        f"tell {cal}\n"
        f"make new event with properties {{summary:{as_str(title)}, start date:s, end date:e, "
        f"location:{as_str(location)}, description:{as_str(notes)}}}\n"
        f"end tell\nend tell", timeout=60)
    return f"event '{title}' added for {begin:%a %d %b %I:%M %p}"


# ---------------------------------------------------------------- Messages


@tool("imessage_send", "Send an iMessage / SMS from the Messages app.",
      {"to": S("phone number (with country code) or Apple ID email"), "text": S("message")},
      ["to", "text"], level=CONFIRM,
      describe=lambda a: f"Send iMessage to {a.get('to')}: \"{a.get('text')}\"")
def imessage_send(to: str, text: str):
    osa(f'tell application "Messages"\n'
        f"try\n"
        f"set svc to 1st account whose service type = iMessage\n"
        f"send {as_str(text)} to participant {as_str(to)} of svc\n"
        f"on error\n"
        f"set svc to 1st service whose service type = iMessage\n"
        f"send {as_str(text)} to buddy {as_str(to)} of svc\n"
        f"end try\nend tell")
    return f"message sent to {to}"


# ---------------------------------------------------------------- Music


@tool("music_control", "Control Apple Music: play/pause/next/previous, or play a song/artist/playlist by name.",
      {"action": E("action", ["play", "pause", "next", "previous", "play_song", "play_playlist", "now_playing"]),
       "query": S("song, artist or playlist name for play_song / play_playlist")},
      ["action"])
def music_control(action: str, query: str = ""):
    if action in ("play", "pause"):
        osa(f'tell application "Music" to {action}')
    elif action == "next":
        osa('tell application "Music" to next track')
    elif action == "previous":
        osa('tell application "Music" to previous track')
    elif action == "now_playing":
        return osa('tell application "Music"\nif player state is playing then\n'
                   'return (name of current track) & " — " & (artist of current track)\n'
                   'else\nreturn "nothing playing"\nend if\nend tell')
    elif action == "play_playlist":
        osa(f'tell application "Music" to play playlist {as_str(query)}')
        return f"playing playlist {query}"
    elif action == "play_song":
        out = osa(f'tell application "Music"\n'
                  f"set hits to (every track of library playlist 1 whose name contains {as_str(query)} "
                  f"or artist contains {as_str(query)})\n"
                  f'if hits is {{}} then return "none"\n'
                  f"play item 1 of hits\n"
                  f'return (name of item 1 of hits) & " — " & (artist of item 1 of hits)\nend tell', timeout=60)
        if out == "none":
            return f"'{query}' isn't in your Music library — try play_youtube or spotify_search"
        return f"playing {out}"
    return f"music {action}"


# ---------------------------------------------------------------- Finder / notifications


@tool("finder_reveal", "Show a file or folder selected in a Finder window.", {"path": S("file or folder")}, ["path"])
def finder_reveal(path: str):
    p = resolve(path)
    if not p.exists():
        return f"not found: {p}"
    run(["open", "-R", str(p)])
    return f"revealed {p.name} in Finder"


@tool("say_notification", "Show a macOS notification banner.",
      {"title": S("title"), "text": S("message")}, ["text"])
def say_notification(text: str, title: str = "Jarvis"):
    osa(f"display notification {as_str(text)} with title {as_str(title or 'Jarvis')}")
    return "notification shown"
