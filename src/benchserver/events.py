"""Persistent progress events. Event ids are monotonic per database and back SSE resumption."""

from __future__ import annotations

import sqlite3
from typing import Any

from .db import jdump, jload, now


def emit(conn: sqlite3.Connection, run_id: str, type_: str, payload: dict[str, Any] | None = None) -> int:
    """Append an event. Call inside the transaction that made the state change it reports."""
    cur = conn.execute("INSERT INTO events(run_id, created_at, type, payload_json) VALUES (?,?,?,?)",
                       (run_id, now(), type_, jdump(payload or {})))
    return int(cur.lastrowid or 0)


def fetch(conn: sqlite3.Connection, run_id: str, after_id: int = 0, limit: int = 500) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT event_id, created_at, type, payload_json FROM events WHERE run_id=? AND event_id>? "
        "ORDER BY event_id LIMIT ?", (run_id, after_id, limit)).fetchall()
    return [{"id": r["event_id"], "at": r["created_at"], "type": r["type"],
             "payload": jload(r["payload_json"])} for r in rows]


def last_id(conn: sqlite3.Connection, run_id: str) -> int:
    row = conn.execute("SELECT MAX(event_id) FROM events WHERE run_id=?", (run_id,)).fetchone()
    return int(row[0] or 0)
