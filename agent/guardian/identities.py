from __future__ import annotations

import time
import uuid

from . import vault

_DB_LOCK = vault._DB_LOCK
_STATUSES = {"planned", "provisioning", "active", "paused", "retired"}
_MODES = {"alias", "mailbox", "external"}


def _conn():
    conn = vault._db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS guardian_identities (
          id TEXT PRIMARY KEY,
          label TEXT NOT NULL,
          email TEXT NOT NULL UNIQUE,
          username TEXT NOT NULL,
          provider TEXT NOT NULL,
          mode TEXT NOT NULL,
          purpose TEXT NOT NULL,
          business_engine TEXT NOT NULL,
          agent_id TEXT NOT NULL,
          associated_wallet_id TEXT,
          recovery_email TEXT,
          status TEXT NOT NULL,
          notes_cipher BLOB,
          notes_nonce BLOB,
          created_at INTEGER NOT NULL,
          updated_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_guardian_identity_status ON guardian_identities(status);
        """
    )
    return conn


def list_identities(token: str, *, include_retired: bool = False):
    vault._session_key(token)
    where = "" if include_retired else "WHERE status <> 'retired'"
    with _DB_LOCK:
        conn = _conn()
        try:
            rows = conn.execute(
                f"""SELECT id,label,email,username,provider,mode,purpose,business_engine,agent_id,
                    associated_wallet_id,recovery_email,status,created_at,updated_at
                    FROM guardian_identities {where} ORDER BY label COLLATE NOCASE"""
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def create_identity(token: str, *, label: str, email: str, username: str,
                    provider: str = "operator-controlled", mode: str = "mailbox",
                    purpose: str = "Guardian identity", business_engine: str = "",
                    agent_id: str = "", associated_wallet_id: str | None = None,
                    recovery_email: str = "", notes: str = "", status: str = "planned"):
    if status not in _STATUSES or mode not in _MODES:
        raise ValueError("Invalid identity mode or status.")
    vault._session_key(token, elevated_required=(status == "active"))
    label, email, username = label.strip(), email.strip().lower(), username.strip()
    if not label or "@" not in email or not username:
        raise ValueError("Identity label, valid email and username are required.")
    key = vault._session_key(token, elevated_required=(status == "active"))
    nonce, cipher = vault._encrypt(key, notes)
    now = int(time.time())
    identity_id = "identity_" + uuid.uuid4().hex[:16]
    with _DB_LOCK:
        conn = _conn()
        try:
            conn.execute(
                "INSERT INTO guardian_identities(id,label,email,username,provider,mode,purpose,business_engine,agent_id,associated_wallet_id,recovery_email,status,notes_cipher,notes_nonce,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (identity_id, label, email, username, provider.strip() or "operator-controlled", mode,
                 purpose.strip(), business_engine.strip(), agent_id.strip(), associated_wallet_id,
                 recovery_email.strip(), status, cipher, nonce, now, now),
            )
            conn.commit()
        except Exception as exc:
            raise ValueError("Identity email already exists or could not be registered.") from exc
        finally:
            conn.close()
    vault._audit("identity_create", result="success", credential_id=identity_id, label=label,
                 consumer="guardian", purpose=purpose, reason=f"{mode}/{status}")
    return next(x for x in list_identities(token, include_retired=True) if x["id"] == identity_id)


def update_identity_status(token: str, identity_id: str, status: str) -> bool:
    if status not in _STATUSES:
        raise ValueError("Invalid identity status.")
    vault._session_key(token, elevated_required=(status == "active"))
    with _DB_LOCK:
        conn = _conn()
        try:
            cur = conn.execute("UPDATE guardian_identities SET status=?,updated_at=? WHERE id=?",
                               (status, int(time.time()), identity_id))
            conn.commit()
            ok = cur.rowcount > 0
        finally:
            conn.close()
    vault._audit("identity_status", result="success" if ok else "noop", credential_id=identity_id, reason=status)
    return ok


def provisionability():
    return {
        "ready": False,
        "mode": "operator_controlled",
        "message": "Identity Factory manages approved mailboxes/aliases and relationships. External provider provisioning requires an explicit connector/API.",
    }
