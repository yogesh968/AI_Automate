"""Gmail + Google Calendar. One-time setup: put an OAuth 'Desktop app' client file at
<data dir>/google_credentials.json (see README). The first call opens a browser to sign in."""

from __future__ import annotations

import base64
import datetime as dt
from email.mime.text import MIMEText

from ..paths import data_file
from .base import CONFIRM, I, S, tool

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
]

SETUP_HELP = (
    "Google isn't connected yet. Setup: 1) console.cloud.google.com → new project → enable Gmail API and "
    "Google Calendar API. 2) OAuth consent screen → External → add yourself as test user. "
    "3) Credentials → Create OAuth client ID → Desktop app → download JSON. "
    f"4) Save it as {data_file('google_credentials.json')} and ask again."
)


def _creds():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    token_path = data_file("google_token.json")
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        cred_file = data_file("google_credentials.json")
        if not cred_file.exists():
            raise FileNotFoundError(SETUP_HELP)
        flow = InstalledAppFlow.from_client_secrets_file(str(cred_file), SCOPES)
        creds = flow.run_local_server(port=0, open_browser=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _svc(name: str, version: str):
    from googleapiclient.discovery import build

    return build(name, version, credentials=_creds(), cache_discovery=False)


def _safe(fn):
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except FileNotFoundError as exc:
            return str(exc)
    wrapper.__name__ = fn.__name__
    return wrapper


# ---------------------------------------------------------------- Gmail


@tool("gmail_list", "List recent emails (default: unread in inbox). Supports Gmail search syntax.",
      {"query": S("Gmail search, default 'is:unread in:inbox'"), "max_results": I("default 10")})
@_safe
def gmail_list(query: str = "is:unread in:inbox", max_results: int = 10):
    gm = _svc("gmail", "v1")
    res = gm.users().messages().list(userId="me", q=query, maxResults=max(1, min(int(max_results), 30))).execute()
    out = []
    for m in res.get("messages", []):
        msg = gm.users().messages().get(userId="me", id=m["id"], format="metadata",
                                        metadataHeaders=["From", "Subject", "Date"]).execute()
        headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
        out.append({"id": m["id"], "from": headers.get("From"), "subject": headers.get("Subject"),
                    "date": headers.get("Date"), "snippet": msg.get("snippet")})
    return out or "no matching emails"


def _body(payload) -> str:
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", "replace")
    for part in payload.get("parts", []) or []:
        text = _body(part)
        if text:
            return text
    return ""


@tool("gmail_read", "Read the full text of one email by id (from gmail_list). Marks it as read.",
      {"message_id": S("email id")}, ["message_id"])
@_safe
def gmail_read(message_id: str):
    gm = _svc("gmail", "v1")
    msg = gm.users().messages().get(userId="me", id=message_id, format="full").execute()
    headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
    gm.users().messages().modify(userId="me", id=message_id, body={"removeLabelIds": ["UNREAD"]}).execute()
    return {"from": headers.get("From"), "to": headers.get("To"), "subject": headers.get("Subject"),
            "date": headers.get("Date"), "body": _body(msg["payload"])[:10000] or msg.get("snippet")}


@tool("gmail_send", "Send an email from the user's Gmail.",
      {"to": S("recipient email"), "subject": S("subject"), "body": S("plain-text body"),
       "reply_to_id": S("optional: id of an email this replies to")},
      ["to", "subject", "body"], level=CONFIRM,
      describe=lambda a: f"Send email to {a.get('to')} — \"{a.get('subject')}\":\n{a.get('body', '')[:400]}")
@_safe
def gmail_send(to: str, subject: str, body: str, reply_to_id: str = ""):
    gm = _svc("gmail", "v1")
    mime = MIMEText(body, "plain", "utf-8")
    mime["to"] = to
    mime["subject"] = subject
    payload: dict = {"raw": base64.urlsafe_b64encode(mime.as_bytes()).decode()}
    if reply_to_id:
        orig = gm.users().messages().get(userId="me", id=reply_to_id, format="metadata",
                                         metadataHeaders=["Message-ID"]).execute()
        payload["threadId"] = orig.get("threadId")
    gm.users().messages().send(userId="me", body=payload).execute()
    return f"email sent to {to}"


# ---------------------------------------------------------------- Calendar


@tool("calendar_list", "List upcoming Google Calendar events.",
      {"days": I("how many days ahead, default 1 (today)"), "max_results": I("default 15")})
@_safe
def calendar_list(days: int = 1, max_results: int = 15):
    cal = _svc("calendar", "v3")
    now = dt.datetime.now().astimezone()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + dt.timedelta(days=max(1, int(days)))
    res = cal.events().list(calendarId="primary", timeMin=now.isoformat(), timeMax=end.isoformat(),
                            singleEvents=True, orderBy="startTime", maxResults=int(max_results)).execute()
    out = []
    for e in res.get("items", []):
        out.append({"id": e["id"], "title": e.get("summary", "(no title)"),
                    "start": e["start"].get("dateTime", e["start"].get("date")),
                    "end": e["end"].get("dateTime", e["end"].get("date")),
                    "location": e.get("location"), "meet": e.get("hangoutLink")})
    return out or "no events"


@tool("calendar_create", "Create a Google Calendar event.",
      {"title": S("event title"), "start": S("ISO local datetime, e.g. 2026-10-01T17:00"),
       "duration_minutes": I("default 60"), "description": S("optional"), "location": S("optional"),
       "attendees": {"type": "array", "items": {"type": "string"}, "description": "optional emails to invite"}},
      ["title", "start"], level=CONFIRM,
      describe=lambda a: f"Add calendar event '{a.get('title')}' at {a.get('start')}"
                         + (f" and invite {', '.join(a.get('attendees') or [])}" if a.get("attendees") else ""))
@_safe
def calendar_create(title: str, start: str, duration_minutes: int = 60, description: str = "", location: str = "",
                    attendees: list[str] | None = None):
    cal = _svc("calendar", "v3")
    begin = dt.datetime.fromisoformat(start)
    if begin.tzinfo is None:
        begin = begin.astimezone()
    finish = begin + dt.timedelta(minutes=int(duration_minutes))
    body = {"summary": title, "description": description, "location": location,
            "start": {"dateTime": begin.isoformat()}, "end": {"dateTime": finish.isoformat()}}
    if attendees:
        body["attendees"] = [{"email": a} for a in attendees]
    ev = cal.events().insert(calendarId="primary", body=body, sendUpdates="all" if attendees else "none").execute()
    return f"event created: {ev.get('htmlLink')}"


@tool("calendar_delete", "Delete a Google Calendar event by id (from calendar_list).",
      {"event_id": S("event id")}, ["event_id"], level=CONFIRM,
      describe=lambda a: f"Delete calendar event {a.get('event_id')}")
@_safe
def calendar_delete(event_id: str):
    _svc("calendar", "v3").events().delete(calendarId="primary", eventId=event_id).execute()
    return "event deleted"
