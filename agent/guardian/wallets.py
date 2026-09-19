from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from typing import Any

from . import vault

_DB_LOCK = vault._DB_LOCK
_ALLOWED_ENV = {"sandbox", "production", "other"}
_ALLOWED_APPROVAL = {"sandbox_auto", "operator", "master"}
_SUPPORTED = {
    "evm": {"chains": {"ethereum", "base", "polygon", "bnb", "arbitrum", "optimism"}},
    "solana": {"chains": {"solana"}},
}


def _conn():
    conn = vault._db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS guardian_wallets (
          id TEXT PRIMARY KEY,
          label TEXT NOT NULL,
          provider TEXT NOT NULL,
          wallet_type TEXT NOT NULL,
          chain TEXT NOT NULL,
          network TEXT NOT NULL,
          environment TEXT NOT NULL,
          purpose TEXT NOT NULL,
          address TEXT NOT NULL,
          derivation_path TEXT NOT NULL,
          material_cipher BLOB NOT NULL,
          material_nonce BLOB NOT NULL,
          notes_cipher BLOB,
          notes_nonce BLOB,
          allowed_consumers TEXT NOT NULL,
          approval TEXT NOT NULL,
          spend_limit TEXT NOT NULL DEFAULT '0',
          active INTEGER NOT NULL DEFAULT 1,
          created_at INTEGER NOT NULL,
          updated_at INTEGER NOT NULL,
          last_used_at INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_guardian_wallets_address ON guardian_wallets(address);
        CREATE INDEX IF NOT EXISTS idx_guardian_wallets_active ON guardian_wallets(active);
        """
    )
    return conn


def _keccak(data: bytes) -> bytes:
    from Crypto.Hash import keccak
    k = keccak.new(digest_bits=256)
    k.update(data)
    return k.digest()


def _seed_from_phrase(mnemonic: str) -> bytes:
    from mnemonic import Mnemonic
    return Mnemonic("english").to_seed(mnemonic.strip())


def _hardened_seed(seed: bytes, curve_name: bytes) -> tuple[bytes, bytes]:
    I = hmac.new(curve_name, seed, hashlib.sha512).digest()
    return I[:32], I[32:]


def _hardened_ed25519(seed: bytes, path: list[int]) -> bytes:
    key, chain = _hardened_seed(seed, b"ed25519 seed")
    for idx in path:
        child = idx | 0x80000000
        I = hmac.new(chain, b"\x00" + key + child.to_bytes(4, "big"), hashlib.sha512).digest()
        key, chain = I[:32], I[32:]
    return key


def _secp_pub(priv: bytes, compressed: bool = False) -> bytes:
    from ecdsa import SECP256k1, SigningKey
    raw = SigningKey.from_string(priv, curve=SECP256k1).get_verifying_key().to_string()
    x, y = raw[:32], raw[32:]
    if compressed:
        return (b"\x02" if int.from_bytes(y, "big") % 2 == 0 else b"\x03") + x
    return b"\x04" + raw


def _bip32_secp256k1(seed: bytes, path: list[int]) -> bytes:
    from ecdsa import SECP256k1
    key, chain = _hardened_seed(seed, b"Bitcoin seed")
    for idx in path:
        child = idx | 0x80000000 if idx >= 2**31 else idx
        data = (b"\x00" + key if idx >= 2**31 else _secp_pub(key, True)) + child.to_bytes(4, "big")
        I = hmac.new(chain, data, hashlib.sha512).digest()
        child_int = (int.from_bytes(I[:32], "big") + int.from_bytes(key, "big")) % SECP256k1.order
        if child_int == 0:
            raise ValueError("Invalid derived wallet key.")
        key, chain = child_int.to_bytes(32, "big"), I[32:]
    return key


def _evm_address(priv: bytes) -> str:
    raw = _keccak(_secp_pub(priv)[1:])[-20:].hex()
    hashed = _keccak(raw.encode("ascii")).hex()
    return "0x" + "".join(
        ch.upper() if ch in "abcdef" and int(hashed[i], 16) >= 8 else ch
        for i, ch in enumerate(raw)
    )


def _solana_address(priv: bytes) -> str:
    import base58
    from nacl.signing import SigningKey
    return base58.b58encode(bytes(SigningKey(priv).verify_key)).decode("ascii")


def _derive_wallet(mnemonic: str, wallet_type: str) -> tuple[str, str, str]:
    seed = _seed_from_phrase(mnemonic)
    if wallet_type == "evm":
        path = "m/44'/60'/0'/0/0"
        priv = _bip32_secp256k1(seed, [2**31 + 44, 2**31 + 60, 2**31, 0, 0])
        return _evm_address(priv), path, priv.hex()
    if wallet_type == "solana":
        path = "m/44'/501'/0'/0'"
        priv = _hardened_ed25519(seed, [44, 501, 0, 0])
        return _solana_address(priv), path, priv.hex()
    raise ValueError(f"Unsupported wallet type: {wallet_type}")


def _policy(token: str, environment: str, approval: str) -> None:
    if environment not in _ALLOWED_ENV or approval not in _ALLOWED_APPROVAL:
        raise ValueError("Invalid wallet policy.")
    vault._session_key(
        token,
        elevated_required=(environment == "production" or approval == "master"),
    )


def _public(row) -> dict[str, Any]:
    return {
        "id": row["id"], "label": row["label"], "provider": row["provider"],
        "wallet_type": row["wallet_type"], "chain": row["chain"], "network": row["network"],
        "environment": row["environment"], "purpose": row["purpose"], "address": row["address"],
        "derivation_path": row["derivation_path"],
        "allowed_consumers": json.loads(row["allowed_consumers"] or "[]"),
        "approval": row["approval"], "spend_limit": row["spend_limit"], "active": bool(row["active"]),
        "created_at": row["created_at"], "updated_at": row["updated_at"], "last_used_at": row["last_used_at"],
    }


def _row(token: str, wallet_id: str, include_inactive: bool = False):
    vault._session_key(token)
    where = "" if include_inactive else " AND active=1"
    with _DB_LOCK:
        conn = _conn()
        try:
            row = conn.execute(f"SELECT * FROM guardian_wallets WHERE id=?{where}", (wallet_id,)).fetchone()
            if not row:
                raise ValueError("Wallet not found or inactive.")
            return row
        finally:
            conn.close()


def create_wallet(token: str, *, label: str, provider: str, wallet_type: str, chain: str, network: str,
                  environment: str = "sandbox", purpose: str = "Guardian wallet", approval: str = "sandbox_auto",
                  allowed_consumers: list[str] | None = None, notes: str = "", spend_limit: str = "0") -> dict[str, Any]:
    if not label.strip() or wallet_type not in _SUPPORTED:
        raise ValueError("Wallet label and supported wallet type are required.")
    _policy(token, environment, approval)
    if chain not in _SUPPORTED[wallet_type]["chains"]:
        raise ValueError(f"Unsupported chain for {wallet_type}: {chain}")
    from mnemonic import Mnemonic
    mnemonic = Mnemonic("english").generate(strength=128)
    address, path, private_key = _derive_wallet(mnemonic, wallet_type)
    key = vault._session_key(token, elevated_required=(environment == "production" or approval == "master"))
    material_nonce, material_cipher = vault._encrypt(
        key, json.dumps({"mnemonic": mnemonic, "private_key": private_key}, separators=(",", ":"))
    )
    notes_nonce, notes_cipher = vault._encrypt(key, notes)
    consumers = sorted({str(x).strip() for x in (allowed_consumers or ["guardian"]) if str(x).strip()})
    now = int(time.time())
    wallet_id = "wallet_" + uuid.uuid4().hex[:16]
    with _DB_LOCK:
        conn = _conn()
        try:
            conn.execute(
                """INSERT INTO guardian_wallets
                (id,label,provider,wallet_type,chain,network,environment,purpose,address,derivation_path,
                 material_cipher,material_nonce,notes_cipher,notes_nonce,allowed_consumers,approval,spend_limit,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (wallet_id, label.strip(), provider.strip() or "native", wallet_type, chain, network.strip(),
                 environment, purpose.strip() or "Guardian wallet", address, path, material_cipher, material_nonce,
                 notes_cipher, notes_nonce, json.dumps(consumers), approval, str(spend_limit), now, now),
            )
            conn.commit()
        finally:
            conn.close()
    vault._audit("wallet_create", result="success", credential_id=wallet_id, label=label,
                 consumer="guardian", purpose=purpose, reason=f"{wallet_type}/{chain}/{network}/{environment}")
    return {**_public(_row(token, wallet_id, True)), "recovery_phrase": mnemonic, "private_key": private_key}


def list_wallets(token: str, *, include_inactive: bool = False) -> list[dict[str, Any]]:
    vault._session_key(token)
    where = "" if include_inactive else "WHERE active=1"
    with _DB_LOCK:
        conn = _conn()
        try:
            rows = conn.execute(f"SELECT * FROM guardian_wallets {where} ORDER BY label COLLATE NOCASE").fetchall()
            return [_public(r) for r in rows]
        finally:
            conn.close()


def import_wallet(token: str, *, label: str, provider: str, wallet_type: str, chain: str, network: str,
                  mnemonic: str, environment: str = "sandbox", purpose: str = "Imported Guardian wallet",
                  approval: str = "operator", allowed_consumers: list[str] | None = None,
                  notes: str = "", spend_limit: str = "0") -> dict[str, Any]:
    if not label.strip() or not mnemonic.strip():
        raise ValueError("Wallet label and recovery phrase are required.")
    _policy(token, environment, approval)
    address, path, private_key = _derive_wallet(mnemonic, wallet_type)
    key = vault._session_key(token, elevated_required=(environment == "production" or approval == "master"))
    material_nonce, material_cipher = vault._encrypt(
        key, json.dumps({"mnemonic": mnemonic.strip(), "private_key": private_key}, separators=(",", ":"))
    )
    notes_nonce, notes_cipher = vault._encrypt(key, notes)
    consumers = sorted({str(x).strip() for x in (allowed_consumers or ["guardian"]) if str(x).strip()})
    now = int(time.time())
    wallet_id = "wallet_" + uuid.uuid4().hex[:16]
    with _DB_LOCK:
        conn = _conn()
        try:
            conn.execute(
                """INSERT INTO guardian_wallets
                (id,label,provider,wallet_type,chain,network,environment,purpose,address,derivation_path,
                 material_cipher,material_nonce,notes_cipher,notes_nonce,allowed_consumers,approval,spend_limit,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (wallet_id, label.strip(), provider.strip() or "imported", wallet_type, chain, network.strip(),
                 environment, purpose.strip(), address, path, material_cipher, material_nonce, notes_cipher,
                 notes_nonce, json.dumps(consumers), approval, str(spend_limit), now, now),
            )
            conn.commit()
        finally:
            conn.close()
    vault._audit("wallet_import", result="success", credential_id=wallet_id, label=label,
                 consumer="guardian", purpose=purpose, reason=f"{wallet_type}/{chain}/{network}/{environment}")
    return _public(_row(token, wallet_id, True))


def withdraw_wallet(token: str, wallet_id: str, *, consumer: str, purpose: str, environment: str,
                    ttl_seconds: int = 300, export_recovery: bool = False) -> dict[str, Any]:
    consumer = consumer.strip() or "guardian"
    row = _row(token, wallet_id)
    if environment != row["environment"]:
        raise PermissionError(f"Wallet environment mismatch: stored={row['environment']}, requested={environment}.")
    if consumer not in json.loads(row["allowed_consumers"] or "[]"):
        raise PermissionError("Consumer is not approved for this wallet.")
    elevated = row["environment"] == "production" or row["approval"] == "master" or export_recovery
    key = vault._session_key(token, elevated_required=elevated)
    ttl_seconds = max(30, min(int(ttl_seconds), 3600))
    material = json.loads(vault._decrypt(key, bytes(row["material_nonce"]), bytes(row["material_cipher"])))
    now = int(time.time())
    with _DB_LOCK:
        conn = _conn()
        try:
            conn.execute("UPDATE guardian_wallets SET last_used_at=? WHERE id=?", (now, wallet_id))
            conn.commit()
        finally:
            conn.close()
    vault._audit("wallet_withdraw", result="success", credential_id=wallet_id, label=row["label"],
                 consumer=consumer, purpose=purpose, reason="recovery export" if export_recovery else "signing access")
    out = {
        "wallet_id": wallet_id, "label": row["label"], "wallet_type": row["wallet_type"],
        "chain": row["chain"], "network": row["network"], "address": row["address"],
        "lease_id": "wlease_" + uuid.uuid4().hex[:16], "private_key": material["private_key"],
        "issued_at": now, "expires_at": now + ttl_seconds,
    }
    if export_recovery:
        out["recovery_phrase"] = material["mnemonic"]
    return out


def deactivate_wallet(token: str, wallet_id: str) -> bool:
    row = _row(token, wallet_id, True)
    if row["environment"] == "production" or row["approval"] == "master":
        vault._session_key(token, elevated_required=True)
    with _DB_LOCK:
        conn = _conn()
        try:
            cur = conn.execute("UPDATE guardian_wallets SET active=0,updated_at=? WHERE id=?", (int(time.time()), wallet_id))
            conn.commit()
            ok = cur.rowcount > 0
        finally:
            conn.close()
    vault._audit("wallet_deactivate", result="success" if ok else "noop", credential_id=wallet_id, label=row["label"])
    return ok

def guardian_withdraw_wallet(
    wallet_id: str,
    *,
    consumer: str,
    purpose: str,
    environment: str = "sandbox",
    ttl_seconds: int = 300,
    export_recovery: bool = False,
) -> dict[str, Any]:
    """Native Guardian runtime access path using the device-sealed Vault."""
    vault._purge_sessions()
    candidates = [
        token for token, (_key, _expires, elevated) in vault._ACTIVE.items()
        if not elevated
    ]
    if not candidates:
        vault.auto_unlock()
        vault._purge_sessions()
        candidates = [
            token for token, (_key, _expires, elevated) in vault._ACTIVE.items()
            if not elevated
        ]
    if candidates:
        return withdraw_wallet(
            candidates[0],
            wallet_id,
            consumer=consumer,
            purpose=purpose,
            environment=environment,
            ttl_seconds=ttl_seconds,
            export_recovery=export_recovery,
        )
    raise PermissionError("Guardian Vault is locked and this device has no active Guardian runtime seal.")
