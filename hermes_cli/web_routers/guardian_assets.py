from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from agent.guardian import google_workspace, gmail_external, identities, wallets

router = APIRouter(prefix="/api/guardian/vault", tags=["guardian-vault-assets"])


def _token(request: Request) -> str:
    value = request.headers.get("authorization", "")
    if not value.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Vault session required.")
    return value[7:].strip()


class WalletCreate(BaseModel):
    label: str
    provider: str = "native"
    wallet_type: str = "evm"
    chain: str = "ethereum"
    network: str = "mainnet"
    environment: str = "sandbox"
    purpose: str = "Guardian wallet"
    approval: str = "sandbox_auto"
    allowed_consumers: list[str] = Field(default_factory=lambda: ["guardian"])
    notes: str = ""
    spend_limit: str = "0"


class WalletImport(WalletCreate):
    mnemonic: str


class WalletWithdraw(BaseModel):
    consumer: str = "guardian"
    purpose: str = "Guardian-approved signing operation"
    environment: str = "sandbox"
    ttl_seconds: int = 300
    export_recovery: bool = False


class IdentityCreate(BaseModel):
    label: str
    email: str
    username: str
    provider: str = "operator-controlled"
    mode: str = "mailbox"
    purpose: str = "Guardian identity"
    business_engine: str = ""
    agent_id: str = ""
    associated_wallet_id: str | None = None
    recovery_email: str = ""
    notes: str = ""
    status: str = "planned"


class IdentityStatus(BaseModel):
    status: str


class WorkspaceProvision(BaseModel):
    service_credential_id: str
    primary_email: str
    given_name: str
    family_name: str
    password: str
    customer_id: str = "my_customer"


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Guardian Vault asset error: {exc}")


@router.get("/wallets")
def get_wallets(request: Request):
    return {"wallets": _call(wallets.list_wallets, _token(request))}


@router.post("/wallets")
def create_wallet(request: Request, body: WalletCreate):
    return _call(wallets.create_wallet, _token(request), **body.model_dump())


@router.post("/wallets/import")
def import_wallet(request: Request, body: WalletImport):
    return _call(wallets.import_wallet, _token(request), **body.model_dump())


@router.post("/wallets/{wallet_id}/withdraw")
def withdraw_wallet(request: Request, wallet_id: str, body: WalletWithdraw):
    return _call(wallets.withdraw_wallet, _token(request), wallet_id, **body.model_dump())


@router.delete("/wallets/{wallet_id}")
def deactivate_wallet(request: Request, wallet_id: str):
    return {"ok": _call(wallets.deactivate_wallet, _token(request), wallet_id)}


@router.get("/identities")
def get_identities(request: Request):
    return {"identities": _call(identities.list_identities, _token(request))}


@router.post("/identities")
def create_identity(request: Request, body: IdentityCreate):
    return _call(identities.create_identity, _token(request), **body.model_dump())


@router.post("/identities/{identity_id}/status")
def identity_status(request: Request, identity_id: str, body: IdentityStatus):
    return {"ok": _call(identities.update_identity_status, _token(request), identity_id, body.status)}


@router.get("/identity-factory/status")
def identity_factory_status():
    return identities.provisionability()


@router.get("/gmail-external/status")
def gmail_external_status():
    return gmail_external.status()


@router.get("/workspace/status")
def workspace_status():
    return google_workspace.capabilities()


@router.post("/workspace/users")
def workspace_create_user(request: Request, body: WorkspaceProvision):
    return _call(google_workspace.provision_user, _token(request), **body.model_dump())
