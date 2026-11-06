"""Event tracker for the Crypto Intelligence Department.

Tracks crypto events, deadlines, and provides notification-ready
deadline approaching alerts.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)

_EVENT_SCHEMA = """
CREATE TABLE IF NOT EXISTS crypto_events (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    event_type TEXT NOT NULL DEFAULT 'other',
    project TEXT DEFAULT '',
    chain TEXT DEFAULT '',
    start_time TEXT NOT NULL,
    end_time TEXT DEFAULT NULL,
    importance TEXT DEFAULT 'normal',
    source_url TEXT DEFAULT '',
    notified INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    notes TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_event_type ON crypto_events(event_type);
CREATE INDEX IF NOT EXISTS idx_event_end ON crypto_events(end_time);
"""


class EventTracker:
    """Tracks crypto events and deadlines with SQLite persistence."""

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self._base_dir = base_dir or (get_hermes_home() / "crypto_intel")
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._base_dir / "events.db"
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self._db_path), timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn = conn
        return conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.executescript(_EVENT_SCHEMA)
        conn.commit()

    def add_event(
        self,
        title: str,
        event_type: str = "other",
        description: str = "",
        project: str = "",
        chain: str = "",
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        importance: str = "normal",
        source_url: str = "",
        notes: str = "",
    ) -> str:
        """Add a crypto event. Returns event ID."""
        event_id = str(uuid.uuid4())[:12]
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO crypto_events
            (id, title, description, event_type, project, chain,
             start_time, end_time, importance, source_url, created_at, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id, title, description, event_type, project, chain,
                start_time or now, end_time, importance, source_url, now, notes,
            ),
        )
        conn.commit()
        return event_id

    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM crypto_events WHERE id = ?", (event_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_events(
        self,
        event_type: Optional[str] = None,
        project: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        query = "SELECT * FROM crypto_events WHERE 1=1"
        params: list = []
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)
        if project:
            query += " AND project = ?"
            params.append(project)
        query += " ORDER BY end_time ASC NULLS LAST LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_expiring(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get events with end_time approaching."""
        conn = self._get_conn()
        now = datetime.now(timezone.utc).isoformat()
        rows = conn.execute(
            """SELECT * FROM crypto_events
            WHERE end_time IS NOT NULL
            AND julianday(end_time) > julianday(?)
            AND julianday(end_time) < julianday(?, '+' || ? || ' hours')
            AND notified = 0
            ORDER BY end_time ASC""",
            (now, now, str(hours)),
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_notified(self, event_id: str) -> bool:
        conn = self._get_conn()
        cur = conn.execute(
            "UPDATE crypto_events SET notified = 1 WHERE id = ?",
            (event_id,),
        )
        conn.commit()
        return cur.rowcount > 0

    def delete_event(self, event_id: str) -> bool:
        conn = self._get_conn()
        cur = conn.execute(
            "DELETE FROM crypto_events WHERE id = ?", (event_id,)
        )
        conn.commit()
        return cur.rowcount > 0

    def count(self) -> int:
        conn = self._get_conn()
        row = conn.execute("SELECT COUNT(*) as cnt FROM crypto_events").fetchone()
        return row["cnt"] if row else 0

    def summary(self) -> Dict[str, Any]:
        conn = self._get_conn()
        total = conn.execute("SELECT COUNT(*) as cnt FROM crypto_events").fetchone()
        by_type = conn.execute(
            "SELECT event_type, COUNT(*) as cnt FROM crypto_events GROUP BY event_type"
        ).fetchall()
        now = datetime.now(timezone.utc).isoformat()
        expiring = conn.execute(
            """SELECT COUNT(*) as cnt FROM crypto_events
            WHERE end_time IS NOT NULL
            AND julianday(end_time) > julianday(?)
            AND julianday(end_time) < julianday(?, '+24 hours')
            AND notified = 0""",
            (now, now),
        ).fetchone()
        return {
            "total": total["cnt"] if total else 0,
            "by_type": {r["event_type"]: r["cnt"] for r in by_type},
            "expiring_24h": expiring["cnt"] if expiring else 0,
        }
