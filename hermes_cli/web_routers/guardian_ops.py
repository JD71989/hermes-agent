"""Guardian operational surfaces — read-only dashboard routes.

One router for the Guardian capability families the dashboard renders:
revenue, commercial, intelligence, creators, marketing, crypto, trading,
cyberlab, automation, system and storage. Every handler is a read-only
projection over stores that already exist (see :mod:`hermes_cli.guardian_ops`);
nothing here writes, creates a database or returns a secret value.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool

from hermes_cli import guardian_ops
from hermes_cli.web_routers._common import log as _log

router = APIRouter(prefix="/api/guardian", tags=["guardian-ops"])


async def _surface(name: str, fn) -> Dict[str, Any]:
    try:
        return await run_in_threadpool(fn)
    except Exception as exc:  # a surface must degrade, never take the API down
        _log.exception("guardian surface %s failed", name)
        raise HTTPException(status_code=500, detail=f"{name} surface unavailable: {type(exc).__name__}")


@router.get("/revenue")
async def guardian_revenue() -> Dict[str, Any]:
    return await _surface("revenue", guardian_ops.revenue_surface)


@router.get("/commercial")
async def guardian_commercial() -> Dict[str, Any]:
    return await _surface("commercial", guardian_ops.commercial_surface)


@router.get("/intelligence")
async def guardian_intelligence() -> Dict[str, Any]:
    return await _surface("intelligence", guardian_ops.intelligence_surface)


@router.get("/creators")
async def guardian_creators() -> Dict[str, Any]:
    return await _surface("creators", guardian_ops.creators_surface)


@router.get("/marketing")
async def guardian_marketing() -> Dict[str, Any]:
    return await _surface("marketing", guardian_ops.marketing_surface)


@router.get("/crypto")
async def guardian_crypto() -> Dict[str, Any]:
    return await _surface("crypto", guardian_ops.crypto_surface)


@router.get("/trading")
async def guardian_trading() -> Dict[str, Any]:
    return await _surface("trading", guardian_ops.trading_surface)


@router.get("/cyberlab")
async def guardian_cyberlab() -> Dict[str, Any]:
    return await _surface("cyberlab", guardian_ops.cyberlab_surface)


@router.get("/automation")
async def guardian_automation() -> Dict[str, Any]:
    return await _surface("automation", guardian_ops.automation_surface)


@router.get("/system")
async def guardian_system() -> Dict[str, Any]:
    return await _surface("system", guardian_ops.system_surface)


@router.get("/storage")
async def guardian_storage() -> Dict[str, Any]:
    return await _surface("storage", guardian_ops.storage_surface)


@router.get("/storage/databases")
async def guardian_storage_databases(force: bool = False) -> Dict[str, Any]:
    return await _surface(
        "storage-databases",
        lambda: guardian_ops.database_health(force=force),
    )
