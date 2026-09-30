"""SQLite storage: chat history, long-term facts (full-text searchable), reminders, audit log."""

import json
import re
import sqlite3
import threading
import time
from typing import Any

from ..paths import data_file

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    ts REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    created REAL NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(text, content='facts', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
    INSERT INTO facts_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    due REAL NOT NULL,
    repeat TEXT NOT NULL DEFAULT '',
    done INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    tool TEXT NOT NULL,
    args TEXT NOT NULL,
    level TEXT NOT NULL,
    result TEXT NOT NULL,
    ok INTEGER NOT NULL
);
"""

REPEAT_SECONDS = {"hourly": 3600, "daily": 86400, "weekly": 7 * 86400}


class Store:
    def __init__(self) -> None:
        self._db = sqlite3.connect(data_file("jarvis.db"), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(SCHEMA)
            self._db.commit()

    def _exec(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            cur = self._db.execute(sql, params)
            rows = cur.fetchall()
            self._db.commit()
            return rows

    def _insert(self, sql: str, params: tuple) -> int:
        with self._lock:
            cur = self._db.execute(sql, params)
            self._db.commit()
            return int(cur.lastrowid)

    # ---- chat history ----
    def add_message(self, role: str, content: str) -> None:
        if content.strip():
            self._insert("INSERT INTO messages(role, content, ts) VALUES (?,?,?)", (role, content, time.time()))

    def recent_messages(self, limit: int = 16) -> list[dict[str, Any]]:
        rows = self._exec("SELECT role, content, ts FROM messages ORDER BY id DESC LIMIT ?", (limit,))
        return [{"role": r["role"], "text": r["content"], "ts": r["ts"]} for r in reversed(rows)]

    def clear_messages(self) -> None:
        self._exec("DELETE FROM messages")

    # ---- long-term facts ----
    def add_fact(self, text: str) -> int:
        return self._insert("INSERT INTO facts(text, created) VALUES (?,?)", (text.strip(), time.time()))

    def delete_fact(self, fact_id: int) -> bool:
        before = self._exec("SELECT id FROM facts WHERE id=?", (fact_id,))
        self._exec("DELETE FROM facts WHERE id=?", (fact_id,))
        return bool(before)

    def all_facts(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = self._exec("SELECT id, text FROM facts ORDER BY id DESC LIMIT ?", (limit,))
        return [{"id": r["id"], "text": r["text"]} for r in rows]

    def search_facts(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        words = [w for w in re.findall(r"\w+", query, flags=re.UNICODE) if len(w) > 2]
        if not words:
            return []
        match = " OR ".join(f'"{w}"' for w in words[:12])
        try:
            rows = self._exec(
                "SELECT f.id, f.text FROM facts_fts JOIN facts f ON f.id = facts_fts.rowid "
                "WHERE facts_fts MATCH ? ORDER BY rank LIMIT ?",
                (match, limit),
            )
        except sqlite3.OperationalError:
            like = f"%{query}%"
            rows = self._exec("SELECT id, text FROM facts WHERE text LIKE ? LIMIT ?", (like, limit))
        return [{"id": r["id"], "text": r["text"]} for r in rows]

    def facts_for_prompt(self, user_text: str, limit: int = 25) -> list[str]:
        facts = self.all_facts(limit=60)
        if len(facts) <= limit:
            return [f["text"] for f in facts]
        picked: dict[int, str] = {f["id"]: f["text"] for f in self.search_facts(user_text, limit=12)}
        for f in facts:
            if len(picked) >= limit:
                break
            picked.setdefault(f["id"], f["text"])
        return list(picked.values())

    # ---- reminders ----
    def add_reminder(self, text: str, due: float, repeat: str = "") -> int:
        return self._insert("INSERT INTO reminders(text, due, repeat) VALUES (?,?,?)", (text, due, repeat))

    def pending_reminders(self) -> list[dict[str, Any]]:
        rows = self._exec("SELECT id, text, due, repeat FROM reminders WHERE done=0 ORDER BY due")
        return [dict(r) for r in rows]

    def due_reminders(self, now: float) -> list[dict[str, Any]]:
        rows = self._exec("SELECT id, text, due, repeat FROM reminders WHERE done=0 AND due<=?", (now,))
        return [dict(r) for r in rows]

    def complete_reminder(self, rem: dict[str, Any]) -> None:
        step = REPEAT_SECONDS.get(rem.get("repeat") or "")
        if step:
            due = rem["due"]
            now = time.time()
            while due <= now:
                due += step
            self._exec("UPDATE reminders SET due=? WHERE id=?", (due, rem["id"]))
        else:
            self._exec("UPDATE reminders SET done=1 WHERE id=?", (rem["id"],))

    def cancel_reminder(self, rem_id: int) -> bool:
        before = self._exec("SELECT id FROM reminders WHERE id=? AND done=0", (rem_id,))
        self._exec("UPDATE reminders SET done=1 WHERE id=?", (rem_id,))
        return bool(before)

    # ---- audit ----
    def add_audit(self, tool: str, args: dict, level: str, result: str, ok: bool) -> None:
        self._insert(
            "INSERT INTO audit(ts, tool, args, level, result, ok) VALUES (?,?,?,?,?,?)",
            (time.time(), tool, json.dumps(args, ensure_ascii=False)[:4000], level, result[:4000], int(ok)),
        )

    def recent_audit(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._exec("SELECT ts, tool, args, level, result, ok FROM audit ORDER BY id DESC LIMIT ?", (limit,))
        out = []
        for r in rows:
            try:
                args = json.loads(r["args"])
            except Exception:
                args = r["args"]
            out.append({"ts": r["ts"], "tool": r["tool"], "args": args, "level": r["level"],
                        "result": r["result"], "ok": bool(r["ok"])})
        return out
