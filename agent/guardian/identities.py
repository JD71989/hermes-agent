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
          credential_id TEXT,
          status TEXT NOT NULL,
          notes_cipher BLOB,
          notes_nonce BLOB,
          created_at INTEGER NOT NULL,
          updated_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_guardian_identity_status ON guardian_identities(status);
        """
    )
    cols = {row[1] for row in conn.execute("PRAGMA table_info(guardian_identities)").fetchall()}
    if "credential_id" not in cols:
        conn.execute("ALTER TABLE guardian_identities ADD COLUMN credential_id TEXT")
        conn.commit()
    return conn


def list_identities(token: str, *, include_retired: bool = False):
    vault._session_key(token)
    where = "" if include_retired else "WHERE status <> 'retired'"
    with _DB_LOCK:
        conn = _conn()
        try:
            rows = conn.execute(
                f"""SELECT id,label,email,username,provider,mode,purpose,business_engine,agent_id,
                    associated_wallet_id,recovery_email,credential_id,status,created_at,updated_at
                    FROM guardian_identities {where} ORDER BY label COLLATE NOCASE"""
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def create_identity(token: str, *, label: str, email: str, username: str,
                    provider: str = "operator-controlled", mode: str = "mailbox",
                    purpose: str = "Guardian identity", business_engine: str = "",
                    agent_id: str = "", associated_wallet_id: str | None = None,
                    recovery_email: str = "", credential_id: str | None = None,
                    notes: str = "", status: str = "planned"):
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
                "INSERT INTO guardian_identities(id,label,email,username,provider,mode,purpose,business_engine,agent_id,associated_wallet_id,recovery_email,credential_id,status,notes_cipher,notes_nonce,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (identity_id, label, email, username, provider.strip() or "operator-controlled", mode,
                 purpose.strip(), business_engine.strip(), agent_id.strip(), associated_wallet_id,
                 recovery_email.strip(), credential_id, status, cipher, nonce, now, now),
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


def _set_identity_state(identity_id: str, status: str, reason: str) -> None:
    with _DB_LOCK:
        conn = _conn()
        try:
            conn.execute(
                "UPDATE guardian_identities SET status=?,updated_at=? WHERE id=?",
                (status, int(time.time()), identity_id),
            )
            conn.commit()
        finally:
            conn.close()
    vault._audit("identity_provision_state", result=status, credential_id=identity_id, reason=reason[:300])


def provision_workspace_identity(
    token: str,
    *,
    service_credential_id: str,
    admin_email: str,
    label: str,
    primary_email: str,
    username: str,
    given_name: str,
    family_name: str,
    business_engine: str = "",
    agent_id: str = "",
    associated_wallet_id: str | None = None,
    recovery_email: str = "",
    purpose: str = "Guardian Workspace identity",
    customer_id: str = "my_customer",
    password: str = "",
) -> dict:
    """Provision one admin-controlled Workspace identity and register its Vault credential."""
    vault._session_key(token, elevated_required=True)
    from . import workspace

    primary_email = primary_email.strip().lower()
    username = username.strip()
    admin_email = admin_email.strip().lower()
    label = label.strip()
    if not service_credential_id:
        raise ValueError("A Vault service-account credential is required.")
    if not admin_email or "@" not in admin_email:
        raise ValueError("A Workspace admin email is required for service-account delegation.")
    if not primary_email or "@" not in primary_email:
        raise ValueError("A valid Workspace primary email is required.")
    if not username:
        raise ValueError("Identity username is required.")
    if not label:
        raise ValueError("Identity label is required.")
    if not given_name.strip() or not family_name.strip():
        raise ValueError("Given and family names are required.")

    generated = not bool(password)
    password = password or vault.generate_password(24)
    identity = create_identity(
        token,
        label=label,
        email=primary_email,
        username=username,
        provider="google_workspace",
        mode="mailbox",
        purpose=purpose,
        business_engine=business_engine,
        agent_id=agent_id,
        associated_wallet_id=associated_wallet_id,
        recovery_email=recovery_email,
        notes="Provisioned by Guardian Identity Factory; credential stored in Guardian Vault.",
        status="provisioning",
    )
    credential = vault.save_credential(
        token,
        credential_id=None,
        label=f"Workspace login | {primary_email}",
        kind="login",
        environment="production",
        username=primary_email,
        secret=password,
        url="https://accounts.google.com/",
        notes=f"Guardian Workspace identity for {label}. Generated={generated}.",
        allowed_consumers=["guardian"],
        approval="operator",
        rotated=False,
    )

    with _DB_LOCK:
        conn = _conn()
        try:
            conn.execute(
                "UPDATE guardian_identities SET credential_id=?,updated_at=? WHERE id=?",
                (credential["id"], int(time.time()), identity["id"]),
            )
            conn.commit()
        finally:
            conn.close()

    try:
        result = workspace.provision_user(
            token,
            service_credential_id=service_credential_id,
            admin_email=admin_email,
            primary_email=primary_email,
            given_name=given_name,
            family_name=family_name,
            password=password,
            customer_id=customer_id,
        )
    except Exception as exc:
        _set_identity_state(identity["id"], "paused", f"Workspace provisioning failed: {exc}")
        raise

    if not result.get("verified"):
        _set_identity_state(identity["id"], "paused", "Workspace user creation returned without verification.")
        return {
            "ok": False,
            "ready_for_automation": False,
            "identity_id": identity["id"],
            "credential_id": credential["id"],
            "primary_email": primary_email,
            "verified": False,
            "password_generated": generated,
            "message": "Workspace user was created but Guardian could not verify the resulting user record.",
        }

    with _DB_LOCK:
        conn = _conn()
        try:
            conn.execute(
                "UPDATE guardian_identities SET status='active',updated_at=? WHERE id=?",
                (int(time.time()), identity["id"]),
            )
            conn.commit()
        finally:
            conn.close()

    vault._audit(
        "identity_provision_workspace",
        result="success",
        credential_id=credential["id"],
        label=label,
        consumer="guardian",
        purpose=purpose,
        reason="verified Workspace mailbox",
    )
    final_identity = next(
        x for x in list_identities(token, include_retired=True) if x["id"] == identity["id"]
    )
    return {
        "ok": True,
        "ready_for_automation": True,
        "identity": final_identity,
        "credential_id": credential["id"],
        "primary_email": primary_email,
        "verified": True,
        "password_generated": generated,
        "message": "Workspace identity provisioned, verified, and marked ready for automation. Password is stored only in Guardian Vault.",
    }


def provisionability():
    return {
        "ready": True,
        "mode": "operator_controlled",
        "message": "One-click Google Workspace provisioning is available for domains you control when a Vault-held service account with domain-wide delegation and an admin subject is configured.",
    }
