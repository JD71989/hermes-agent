from __future__ import annotations

import base64
import ctypes
import json
import os
import secrets
import sqlite3
import string
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt


_DB_LOCK = threading.RLock()
_SESSION_TTL = 30 * 60
_ALLOWED_KINDS = {"login", "api_key", "token", "ssh_key", "certificate", "master_key", "other"}
_ALLOWED_ENVIRONMENTS = {"sandbox", "production", "other"}
_ALLOWED_APPROVALS = {"sandbox_auto", "operator", "master"}
_ACTIVE: dict[str, tuple[bytes, float, bool]] = {}


def _home() -> Path:
    try:
        from hermes_constants import get_hermes_home
        return get_hermes_home()
    except Exception:
        return Path(os.path.expanduser("~/.hermes"))


def _db_path() -> Path:
    return _home() / "guardian" / "vault.db"


def _now() -> int:
    return int(time.time())


def _db() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS vault_meta (
          id INTEGER PRIMARY KEY CHECK(id=1),
          salt BLOB NOT NULL,
          wrapped_key BLOB NOT NULL,
          wrap_nonce BLOB NOT NULL,
          dpapi_key BLOB,
          created_at INTEGER NOT NULL,
          updated_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS credentials (
          id TEXT PRIMARY KEY,
          label TEXT NOT NULL,
          kind TEXT NOT NULL,
          environment TEXT NOT NULL,
          username_cipher BLOB,
          username_nonce BLOB,
          secret_cipher BLOB NOT NULL,
          secret_nonce BLOB NOT NULL,
          url TEXT,
          notes_cipher BLOB,
          notes_nonce BLOB,
          allowed_consumers TEXT NOT NULL,
          approval TEXT NOT NULL,
          active INTEGER NOT NULL DEFAULT 1,
          created_at INTEGER NOT NULL,
          updated_at INTEGER NOT NULL,
          last_used_at INTEGER,
          last_rotated_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS withdrawals (
          id TEXT PRIMARY KEY,
          credential_id TEXT NOT NULL REFERENCES credentials(id) ON DELETE CASCADE,
          consumer TEXT NOT NULL,
          purpose TEXT NOT NULL,
          environment TEXT NOT NULL,
          issued_at INTEGER NOT NULL,
          expires_at INTEGER NOT NULL,
          revoked INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS vault_audit (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          at INTEGER NOT NULL,
          action TEXT NOT NULL,
          credential_id TEXT,
          label TEXT,
          consumer TEXT,
          purpose TEXT,
          result TEXT NOT NULL,
          reason TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_credentials_label ON credentials(label);
        CREATE INDEX IF NOT EXISTS idx_withdrawals_expiry ON withdrawals(expires_at, revoked);
        CREATE INDEX IF NOT EXISTS idx_audit_at ON vault_audit(at DESC);
        """
    )
    return conn


def _derive(passphrase: str, salt: bytes) -> bytes:
    if len(passphrase) < 14:
        raise ValueError("Master passphrase must be at least 14 characters.")
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(passphrase.encode("utf-8"))


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii"))


def _dpapi_protect(data: bytes) -> bytes | None:
    if os.name != "nt":
        return None
    try:
        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]
        raw = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        inp = DATA_BLOB(len(data), raw)
        out = DATA_BLOB()
        crypt32 = ctypes.windll.crypt32
        if not crypt32.CryptProtectData(ctypes.byref(inp), None, None, None, None, 0, ctypes.byref(out)):
            return None
        try:
            return ctypes.string_at(out.pbData, out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(out.pbData)
    except Exception:
        return None


def _dpapi_unprotect(data: bytes) -> bytes | None:
    if os.name != "nt":
        return None
    try:
        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]
        raw = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        inp = DATA_BLOB(len(data), raw)
        out = DATA_BLOB()
        crypt32 = ctypes.windll.crypt32
        if not crypt32.CryptUnprotectData(ctypes.byref(inp), None, None, None, None, 0, ctypes.byref(out)):
            return None
        try:
            return ctypes.string_at(out.pbData, out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(out.pbData)
    except Exception:
        return None


def _purge_sessions() -> None:
    now = time.time()
    for token, (_key, expires, _elevated) in list(_ACTIVE.items()):
        if expires <= now:
            _ACTIVE.pop(token, None)


def _session_key(token: str, *, elevated_required: bool = False) -> bytes:
    with _DB_LOCK:
        _purge_sessions()
        item = _ACTIVE.get(token)
        if not item:
            raise PermissionError("Vault is locked or the unlock session expired.")
        key, expires, elevated = item
        if expires <= time.time():
            _ACTIVE.pop(token, None)
            raise PermissionError("Vault unlock session expired.")
        _ACTIVE[token] = (key, time.time() + _SESSION_TTL, elevated)
        if elevated_required and not elevated:
            raise PermissionError("Elevated vault authorization is required for this credential.")
        return key


def _encrypt(key: bytes, text: str) -> tuple[bytes, bytes]:
    nonce = secrets.token_bytes(12)
    return nonce, AESGCM(key).encrypt(nonce, text.encode("utf-8"), None)


def _decrypt(key: bytes, nonce: bytes, cipher: bytes) -> str:
    return AESGCM(key).decrypt(nonce, cipher, None).decode("utf-8")


def _audit(action: str, *, result: str, credential_id: str | None = None, label: str | None = None,
           consumer: str | None = None, purpose: str | None = None, reason: str | None = None) -> None:
    with _DB_LOCK:
        conn = _db()
        try:
            conn.execute(
                "INSERT INTO vault_audit(at,action,credential_id,label,consumer,purpose,result,reason) VALUES (?,?,?,?,?,?,?,?)",
                (_now(), action, credential_id, label, consumer, purpose, result, reason),
            )
            conn.commit()
        finally:
            conn.close()


def status() -> dict[str, Any]:
    with _DB_LOCK:
        conn = _db()
        try:
            meta = conn.execute("SELECT * FROM vault_meta WHERE id=1").fetchone()
            count = int(conn.execute("SELECT COUNT(*) FROM credentials WHERE active=1").fetchone()[0])
        finally:
            conn.close()
        _purge_sessions()
        return {
            "configured": bool(meta),
            "unlocked": bool(_ACTIVE),
            "credential_count": count,
            "runtime_auto_unlock": bool(meta and meta["dpapi_key"]),
            "db_path": str(_db_path()),
            "session_ttl_seconds": _SESSION_TTL,
        }


def setup(passphrase: str, *, authorize_runtime: bool = True) -> dict[str, Any]:
    with _DB_LOCK:
        conn = _db()
        try:
            if conn.execute("SELECT 1 FROM vault_meta WHERE id=1").fetchone():
                raise ValueError("Vault is already configured.")
            salt = secrets.token_bytes(16)
            data_key = secrets.token_bytes(32)
            wrap_key = _derive(passphrase, salt)
            nonce, wrapped = _encrypt(wrap_key, _b64(data_key))
            dpapi_key = _dpapi_protect(data_key) if authorize_runtime else None
            now = _now()
            conn.execute(
                "INSERT INTO vault_meta(id,salt,wrapped_key,wrap_nonce,dpapi_key,created_at,updated_at) VALUES (1,?,?,?,?,?,?)",
                (salt, wrapped, nonce, dpapi_key, now, now),
            )
            conn.commit()
        finally:
            conn.close()
    _ACTIVE.clear()
    token = _issue_session(data_key, elevated=True)
    _audit("setup", result="success", reason="Vault initialized.")
    return {
        "token": token,
        "status": status(),
        "runtime_auto_unlock": bool(dpapi_key),
    }


def _issue_session(data_key: bytes, *, elevated: bool) -> str:
    token = _b64(secrets.token_bytes(32))
    with _DB_LOCK:
        _ACTIVE[token] = (data_key, time.time() + _SESSION_TTL, elevated)
    return token


def unlock(passphrase: str, *, elevated: bool = False) -> dict[str, Any]:
    with _DB_LOCK:
        conn = _db()
        try:
            meta = conn.execute("SELECT * FROM vault_meta WHERE id=1").fetchone()
        finally:
            conn.close()
    if not meta:
        raise ValueError("Vault is not configured.")
    wrap_key = _derive(passphrase, bytes(meta["salt"]))
    try:
        encoded = AESGCM(wrap_key).decrypt(bytes(meta["wrap_nonce"]), bytes(meta["wrapped_key"]), None)
        data_key = _unb64(encoded.decode("utf-8"))
    except Exception as exc:
        _audit("unlock", result="denied", reason="Invalid master passphrase.")
        raise PermissionError("Invalid master passphrase.") from exc
    token = _issue_session(data_key, elevated=elevated)
    _audit("unlock", result="success", reason="Master passphrase accepted.")
    return {"token": token, "status": status(), "elevated": elevated}


def auto_unlock() -> bool:
    with _DB_LOCK:
        conn = _db()
        try:
            meta = conn.execute("SELECT dpapi_key FROM vault_meta WHERE id=1").fetchone()
        finally:
            conn.close()
    if not meta or not meta["dpapi_key"]:
        return False
    data_key = _dpapi_unprotect(bytes(meta["dpapi_key"]))
    if not data_key:
        return False
    _issue_session(data_key, elevated=False)
    _audit("auto_unlock", result="success", reason="Windows device seal accepted.")
    return True


def lock() -> None:
    with _DB_LOCK:
        _ACTIVE.clear()
    _audit("lock", result="success", reason="All vault sessions cleared.")


def list_credentials(token: str, *, include_inactive: bool = False) -> list[dict[str, Any]]:
    _session_key(token)
    with _DB_LOCK:
        conn = _db()
        try:
            where = "" if include_inactive else "WHERE active=1"
            rows = conn.execute(
                f"SELECT id,label,kind,environment,url,allowed_consumers,approval,active,created_at,updated_at,last_used_at,last_rotated_at "
                f"FROM credentials {where} ORDER BY label COLLATE NOCASE"
            ).fetchall()
            return [
                {
                    "id": r["id"], "label": r["label"], "kind": r["kind"],
                    "environment": r["environment"], "url": r["url"] or "",
                    "allowed_consumers": json.loads(r["allowed_consumers"] or "[]"),
                    "approval": r["approval"], "active": bool(r["active"]),
                    "created_at": r["created_at"], "updated_at": r["updated_at"],
                    "last_used_at": r["last_used_at"], "last_rotated_at": r["last_rotated_at"],
                } for r in rows
            ]
        finally:
            conn.close()


def save_credential(
    token: str,
    *,
    credential_id: str | None,
    label: str,
    kind: str,
    environment: str,
    username: str,
    secret: str,
    url: str = "",
    notes: str = "",
    allowed_consumers: list[str] | None = None,
    approval: str = "sandbox_auto",
    rotated: bool = False,
) -> dict[str, Any]:
    label = label.strip()
    if not label or not secret:
        raise ValueError("Label and secret are required.")
    kind = kind if kind in _ALLOWED_KINDS else "other"
    environment = environment if environment in _ALLOWED_ENVIRONMENTS else "other"
    approval = approval if approval in _ALLOWED_APPROVALS else "operator"
    key = _session_key(token, elevated_required=(approval == "master" or environment == "production"))
    consumers = sorted({str(x).strip() for x in (allowed_consumers or []) if str(x).strip()})
    if not consumers:
        consumers = ["guardian"]
    un, uc = _encrypt(key, username)
    nn, nc = _encrypt(key, notes)
    sn, sc = _encrypt(key, secret)
    now = _now()
    cid = credential_id or ("cred_" + uuid.uuid4().hex[:16])
    with _DB_LOCK:
        conn = _db()
        try:
            if credential_id:
                conn.execute(
                    """UPDATE credentials SET label=?,kind=?,environment=?,username_cipher=?,username_nonce=?,
                    secret_cipher=?,secret_nonce=?,url=?,notes_cipher=?,notes_nonce=?,allowed_consumers=?,approval=?,
                    updated_at=?,last_rotated_at=? WHERE id=?""",
                    (label, kind, environment, uc, un, sc, sn, url.strip(), nc, nn, json.dumps(consumers), approval,
                     now, now if rotated else None, cid),
                )
                if conn.total_changes == 0:
                    raise ValueError("Credential not found.")
            else:
                conn.execute(
                    """INSERT INTO credentials(id,label,kind,environment,username_cipher,username_nonce,secret_cipher,secret_nonce,
                    url,notes_cipher,notes_nonce,allowed_consumers,approval,created_at,updated_at,last_rotated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (cid, label, kind, environment, uc, un, sc, sn, url.strip(), nc, nn, json.dumps(consumers), approval, now, now, now if rotated else None),
                )
            conn.commit()
        finally:
            conn.close()
    _audit("save_credential", result="success", credential_id=cid, label=label, reason=f"{environment}/{approval}")
    return next(x for x in list_credentials(token, include_inactive=True) if x["id"] == cid)


def delete_credential(token: str, credential_id: str) -> bool:
    key = _session_key(token)
    with _DB_LOCK:
        conn = _db()
        try:
            row = conn.execute("SELECT label,environment,approval FROM credentials WHERE id=?", (credential_id,)).fetchone()
            if not row:
                return False
            if row["environment"] == "production" or row["approval"] == "master":
                key = _session_key(token, elevated_required=True)
            conn.execute("UPDATE credentials SET active=0,updated_at=? WHERE id=?", (_now(), credential_id))
            conn.commit()
        finally:
            conn.close()
    _audit("delete_credential", result="success", credential_id=credential_id, label=row["label"])
    return True


def withdraw(
    token: str,
    credential_id: str,
    *,
    consumer: str,
    purpose: str,
    environment: str,
    ttl_seconds: int = 300,
) -> dict[str, Any]:
    key = _session_key(token)
    consumer = consumer.strip() or "guardian"
    purpose = purpose.strip() or "Guardian-approved operation"
    ttl_seconds = max(30, min(int(ttl_seconds), 3600))
    with _DB_LOCK:
        conn = _db()
        try:
            row = conn.execute("SELECT * FROM credentials WHERE id=? AND active=1", (credential_id,)).fetchone()
            if not row:
                raise ValueError("Credential not found or inactive.")
            allowed = json.loads(row["allowed_consumers"] or "[]")
            cred_env = row["environment"]
            approval = row["approval"]
            if environment != cred_env and not (environment == "sandbox" and cred_env == "other"):
                raise PermissionError(f"Credential environment mismatch: stored={cred_env}, requested={environment}.")
            if allowed and consumer not in allowed:
                raise PermissionError("Consumer is not approved for this credential.")
            elevated_needed = approval == "master" or cred_env == "production"
            if elevated_needed:
                key = _session_key(token, elevated_required=True)
            username = _decrypt(key, bytes(row["username_nonce"]), bytes(row["username_cipher"])) if row["username_cipher"] else ""
            secret = _decrypt(key, bytes(row["secret_nonce"]), bytes(row["secret_cipher"]))
            now = _now()
            lease_id = "lease_" + uuid.uuid4().hex[:16]
            expires = now + ttl_seconds
            conn.execute(
                "INSERT INTO withdrawals(id,credential_id,consumer,purpose,environment,issued_at,expires_at) VALUES (?,?,?,?,?,?,?)",
                (lease_id, credential_id, consumer, purpose, environment, now, expires),
            )
            conn.execute("UPDATE credentials SET last_used_at=? WHERE id=?", (now, credential_id))
            conn.commit()
        finally:
            conn.close()
    _audit("withdraw", result="success", credential_id=credential_id, label=row["label"], consumer=consumer, purpose=purpose)
    return {
        "lease_id": lease_id,
        "credential_id": credential_id,
        "label": row["label"],
        "kind": row["kind"],
        "environment": cred_env,
        "username": username,
        "secret": secret,
        "url": row["url"] or "",
        "issued_at": now,
        "expires_at": expires,
    }


def revoke_lease(token: str, lease_id: str) -> bool:
    _session_key(token)
    with _DB_LOCK:
        conn = _db()
        try:
            cur = conn.execute("UPDATE withdrawals SET revoked=1 WHERE id=? AND revoked=0", (lease_id,))
            conn.commit()
            ok = cur.rowcount > 0
        finally:
            conn.close()
    _audit("revoke_lease", result="success" if ok else "noop", reason=lease_id)
    return ok


def audit(token: str, limit: int = 100) -> list[dict[str, Any]]:
    _session_key(token)
    with _DB_LOCK:
        conn = _db()
        try:
            rows = conn.execute(
                "SELECT at,action,credential_id,label,consumer,purpose,result,reason FROM vault_audit ORDER BY id DESC LIMIT ?",
                (max(1, min(int(limit), 300)),),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()




def generate_password(length: int = 24) -> str:
    length = max(16, min(int(length), 64))
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_=+"
    while True:
        value = "".join(secrets.choice(alphabet) for _ in range(length))
        if any(c.islower() for c in value) and any(c.isupper() for c in value) and any(c.isdigit() for c in value):
            return value


def guardian_withdraw(
    credential_id: str,
    *,
    consumer: str,
    purpose: str,
    environment: str = "sandbox",
    ttl_seconds: int = 300,
) -> dict[str, Any]:
    """Native executor access path. Operator unlock or device auto-unlock is required."""
    _purge_sessions()
    candidates = [
        token
        for token, (_key, _expires, elevated) in _ACTIVE.items()
        if not elevated
    ]
    if not candidates:
        auto_unlock()
        _purge_sessions()
        candidates = [
            token
            for token, (_key, _expires, elevated) in _ACTIVE.items()
            if not elevated
        ]
    if candidates:
        return withdraw(
            candidates[0],
            credential_id,
            consumer=consumer,
            purpose=purpose,
            environment=environment,
            ttl_seconds=ttl_seconds,
        )
    raise PermissionError("Guardian Vault is locked and this device has no active Guardian runtime seal.")
