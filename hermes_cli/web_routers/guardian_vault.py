from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from agent.guardian import vault

router = APIRouter(prefix="/api/guardian/vault", tags=["guardian-vault"])


class SetupBody(BaseModel):
    passphrase: str = Field(min_length=14, max_length=256)
    authorize_runtime: bool = True


class UnlockBody(BaseModel):
    passphrase: str = Field(min_length=1, max_length=256)
    elevated: bool = False


class CredentialBody(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    kind: str = "login"
    environment: str = "sandbox"
    username: str = ""
    secret: str = Field(min_length=1, max_length=200000)
    url: str = Field(default="", max_length=1000)
    notes: str = Field(default="", max_length=5000)
    allowed_consumers: list[str] = Field(default_factory=list)
    approval: str = "sandbox_auto"
    rotated: bool = False


class WithdrawBody(BaseModel):
    consumer: str = Field(default="guardian", max_length=120)
    purpose: str = Field(default="Guardian-approved sandbox operation", max_length=500)
    environment: str = "sandbox"
    ttl_seconds: int = Field(default=300, ge=30, le=3600)


def _token(auth: Optional[str]) -> str:
    if not auth or not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Vault unlock token required.")
    return auth[7:].strip()


@router.get("/status")
async def get_status():
    return vault.status()


@router.post("/setup")
async def setup(body: SetupBody):
    try:
        return vault.setup(body.passphrase, authorize_runtime=body.authorize_runtime)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/unlock")
async def unlock(body: UnlockBody):
    try:
        return vault.unlock(body.passphrase, elevated=body.elevated)
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/lock")
async def lock(authorization: Optional[str] = Header(default=None)):
    _token(authorization)
    vault.lock()
    return {"ok": True, "status": vault.status()}


@router.get("/credentials")
async def credentials(authorization: Optional[str] = Header(default=None)):
    return {"credentials": vault.list_credentials(_token(authorization))}


@router.post("/credentials")
async def create_credential(body: CredentialBody, authorization: Optional[str] = Header(default=None)):
    try:
        item = vault.save_credential(
            _token(authorization),
            credential_id=None,
            label=body.label,
            kind=body.kind,
            environment=body.environment,
            username=body.username,
            secret=body.secret,
            url=body.url,
            notes=body.notes,
            allowed_consumers=body.allowed_consumers,
            approval=body.approval,
            rotated=body.rotated,
        )
        return item
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/credentials/{credential_id}")
async def update_credential(credential_id: str, body: CredentialBody, authorization: Optional[str] = Header(default=None)):
    try:
        return vault.save_credential(
            _token(authorization),
            credential_id=credential_id,
            label=body.label,
            kind=body.kind,
            environment=body.environment,
            username=body.username,
            secret=body.secret,
            url=body.url,
            notes=body.notes,
            allowed_consumers=body.allowed_consumers,
            approval=body.approval,
            rotated=body.rotated,
        )
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/credentials/{credential_id}")
async def delete_credential(credential_id: str, authorization: Optional[str] = Header(default=None)):
    try:
        ok = vault.delete_credential(_token(authorization), credential_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Credential not found.")
        return {"ok": True}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/credentials/{credential_id}/withdraw")
async def withdraw_credential(
    credential_id: str,
    body: WithdrawBody,
    authorization: Optional[str] = Header(default=None),
):
    try:
        return vault.withdraw(
            _token(authorization),
            credential_id,
            consumer=body.consumer,
            purpose=body.purpose,
            environment=body.environment,
            ttl_seconds=body.ttl_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/leases/{lease_id}/revoke")
async def revoke_lease(lease_id: str, authorization: Optional[str] = Header(default=None)):
    try:
        return {"ok": vault.revoke_lease(_token(authorization), lease_id)}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/audit")
async def get_audit(limit: int = 100, authorization: Optional[str] = Header(default=None)):
    try:
        return {"audit": vault.audit(_token(authorization), limit)}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/generate-password")
async def password_generator(length: int = 24):
    return {"password": vault.generate_password(length)}
