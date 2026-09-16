"""SQLite-backed opportunity store for the Crypto Intelligence Department.

Persists opportunities with full status tracking, deadline management,
and history. Profile-safe (uses get_hermes_home()).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from hermes_constants import get_hermes_home

from agent.crypto_department.opportunity_models import (
    Opportunity,
    OpportunityStatus,
    OpportunityType,
)

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS opportunities (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    project TEXT DEFAULT '',
    chain TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'discovered',
    source_json TEXT DEFAULT '{}',
    scoring_json TEXT DEFAULT '{}',
    result_json TEXT DEFAULT NULL,
    rank INTEGER DEFAULT 0,
    required_actions_json TEXT DEFAULT '[]',
    eligibility_json TEXT DEFAULT '[]',
    eligibility_met INTEGER DEFAULT 0,
    deadline TEXT DEFAULT NULL,
    estimated_reward TEXT DEFAULT '',
    evidence_json TEXT DEFAULT '[]',
    tags_json TEXT DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    notes TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_opp_status ON opportunities(status);
CREATE INDEX IF NOT EXISTS idx_opp_type ON opportunities(type);
CREATE INDEX IF NOT EXISTS idx_opp_deadline ON opportunities(deadline);
CREATE INDEX IF NOT EXISTS idx_opp_project ON opportunities(project);
"""

_HISTORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS opportunity_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_id TEXT NOT NULL,
    old_status TEXT,
    new_status TEXT NOT NULL,
    changed_at TEXT NOT NULL,
    notes TEXT DEFAULT '',
    FOREIGN KEY (opportunity_id) REFERENCES opportunities(id)
);
"""


class OpportunityStore:
    """Thread-safe SQLite store for crypto opportunities."""

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self._base_dir = base_dir or (get_hermes_home() / "crypto_intel")
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._base_dir / "opportunities.db"
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self._db_path), timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.executescript(_SCHEMA)
        conn.executescript(_HISTORY_SCHEMA)
        conn.commit()

    def upsert(self, opp: Opportunity) -> None:
        """Insert or update an opportunity."""
        conn = self._get_conn()
        opp.updated_at = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO opportunities
            (id, type, name, description, project, chain, status,
             source_json, scoring_json, result_json, rank,
             required_actions_json, eligibility_json, eligibility_met,
             deadline, estimated_reward, evidence_json, tags_json,
             created_at, updated_at, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                type=excluded.type, name=excluded.name,
                description=excluded.description, project=excluded.project,
                chain=excluded.chain, status=excluded.status,
                source_json=excluded.source_json,
                scoring_json=excluded.scoring_json,
                result_json=excluded.result_json, rank=excluded.rank,
                required_actions_json=excluded.required_actions_json,
                eligibility_json=excluded.eligibility_json,
                eligibility_met=excluded.eligibility_met,
                deadline=excluded.deadline,
                estimated_reward=excluded.estimated_reward,
                evidence_json=excluded.evidence_json,
                tags_json=excluded.tags_json,
                updated_at=excluded.updated_at, notes=excluded.notes""",
            (
                opp.id, opp.type.value, opp.name, opp.description,
                opp.project, opp.chain, opp.status.value,
                json.dumps(opp.source.to_dict()),
                json.dumps(opp.scoring.to_dict()),
                json.dumps(opp.result.to_dict()) if opp.result else None,
                opp.rank,
                json.dumps(opp.required_actions),
                json.dumps(opp.eligibility),
                1 if opp.eligibility_met else 0,
                opp.deadline, opp.estimated_reward,
                json.dumps(opp.evidence),
                json.dumps(opp.tags),
                opp.created_at, opp.updated_at, opp.notes,
            ),
        )
        conn.commit()

    def get(self, opp_id: str) -> Optional[Opportunity]:
        """Retrieve an opportunity by ID."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM opportunities WHERE id = ?", (opp_id,)
        ).fetchone()
        return self._row_to_opp(row) if row else None

    def list_all(
        self,
        status: Optional[OpportunityStatus] = None,
        opp_type: Optional[OpportunityType] = None,
        project: Optional[str] = None,
        limit: int = 100,
    ) -> List[Opportunity]:
        """List opportunities with optional filters."""
        conn = self._get_conn()
        query = "SELECT * FROM opportunities WHERE 1=1"
        params: list = []
        if status:
            query += " AND status = ?"
            params.append(status.value)
        if opp_type:
            query += " AND type = ?"
            params.append(opp_type.value)
        if project:
            query += " AND project = ?"
            params.append(project)
        query += " ORDER BY rank ASC, updated_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [self._row_to_opp(r) for r in rows]

    def update_status(
        self,
        opp_id: str,
        new_status: OpportunityStatus,
        notes: str = "",
    ) -> bool:
        """Update an opportunity's status with history tracking."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT status FROM opportunities WHERE id = ?", (opp_id,)
        ).fetchone()
        if not row:
            return False
        old_status = row["status"]
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE opportunities SET status = ?, updated_at = ? WHERE id = ?",
            (new_status.value, now, opp_id),
        )
        conn.execute(
            """INSERT INTO opportunity_history
            (opportunity_id, old_status, new_status, changed_at, notes)
            VALUES (?, ?, ?, ?, ?)""",
            (opp_id, old_status, new_status.value, now, notes),
        )
        conn.commit()
        return True

    def get_expiring(self, hours: int = 24) -> List[Opportunity]:
        """Get opportunities with deadlines approaching."""
        conn = self._get_conn()
        now = datetime.now(timezone.utc).isoformat()
        rows = conn.execute(
            """SELECT * FROM opportunities
            WHERE deadline IS NOT NULL
            AND deadline > ?
            AND deadline < datetime(?, '+' || ? || ' hours')
            AND status NOT IN ('expired', 'completed', 'failed', 'skipped')
            ORDER BY deadline ASC""",
            (now, now, str(hours)),
        ).fetchall()
        return [self._row_to_opp(r) for r in rows]

    def get_by_status(self, status: OpportunityStatus) -> List[Opportunity]:
        """Get all opportunities with a given status."""
        return self.list_all(status=status)

    def count(self, status: Optional[OpportunityStatus] = None) -> int:
        conn = self._get_conn()
        if status:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM opportunities WHERE status = ?",
                (status.value,),
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) as cnt FROM opportunities").fetchone()
        return row["cnt"] if row else 0

    def delete(self, opp_id: str) -> bool:
        conn = self._get_conn()
        conn.execute("DELETE FROM opportunity_history WHERE opportunity_id = ?", (opp_id,))
        cur = conn.execute("DELETE FROM opportunities WHERE id = ?", (opp_id,))
        conn.commit()
        return cur.rowcount > 0

    def get_history(self, opp_id: str) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM opportunity_history WHERE opportunity_id = ? ORDER BY changed_at ASC",
            (opp_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def summary(self) -> Dict[str, Any]:
        """Get summary statistics."""
        conn = self._get_conn()
        total = conn.execute("SELECT COUNT(*) as cnt FROM opportunities").fetchone()
        by_status = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM opportunities GROUP BY status"
        ).fetchall()
        by_type = conn.execute(
            "SELECT type, COUNT(*) as cnt FROM opportunities GROUP BY type"
        ).fetchall()
        expiring = conn.execute(
            """SELECT COUNT(*) as cnt FROM opportunities
            WHERE deadline IS NOT NULL
            AND deadline > datetime('now')
            AND deadline < datetime('now', '+24 hours')
            AND status NOT IN ('expired', 'completed', 'failed', 'skipped')"""
        ).fetchone()
        return {
            "total": total["cnt"] if total else 0,
            "by_status": {r["status"]: r["cnt"] for r in by_status},
            "by_type": {r["type"]: r["cnt"] for r in by_type},
            "expiring_24h": expiring["cnt"] if expiring else 0,
        }

    def _row_to_opp(self, row: sqlite3.Row) -> Opportunity:
        d = dict(row)
        opp = Opportunity(
            id=d["id"],
            name=d["name"],
            description=d["description"],
            project=d["project"],
            chain=d["chain"],
            status=OpportunityStatus(d["status"]),
            rank=d["rank"],
            eligibility_met=bool(d["eligibility_met"]),
            deadline=d["deadline"],
            estimated_reward=d["estimated_reward"],
            notes=d["notes"],
            created_at=d["created_at"],
            updated_at=d["updated_at"],
        )
        opp.type = OpportunityType(d["type"])
        try:
            opp.source = opp.source.from_dict(json.loads(d["source_json"]))
        except (json.JSONDecodeError, TypeError):
            pass
        try:
            opp.scoring = opp.scoring.from_dict(json.loads(d["scoring_json"]))
        except (json.JSONDecodeError, TypeError):
            pass
        if d.get("result_json"):
            try:
                from agent.crypto_department.opportunity_models import ScoringResult
                opp.result = ScoringResult.from_dict(json.loads(d["result_json"]))
            except (json.JSONDecodeError, TypeError):
                pass
        try:
            opp.required_actions = json.loads(d["required_actions_json"])
        except (json.JSONDecodeError, TypeError):
            pass
        try:
            opp.eligibility = json.loads(d["eligibility_json"])
        except (json.JSONDecodeError, TypeError):
            pass
        try:
            opp.evidence = json.loads(d["evidence_json"])
        except (json.JSONDecodeError, TypeError):
            pass
        try:
            opp.tags = json.loads(d["tags_json"])
        except (json.JSONDecodeError, TypeError):
            pass
        return opp
