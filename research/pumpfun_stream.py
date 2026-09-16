"""Read-only Solana stream primitives for Pump.fun research."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Any

PUMP_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
PUMPSWAP_PROGRAM_ID = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"


@dataclass(frozen=True)
class LogNotification:
    signature: str
    slot: int
    err: Any
    logs: tuple[str, ...]


def decode_log_notification(payload: dict[str, Any]) -> LogNotification | None:
    if payload.get("method") != "logsNotification":
        return None
    value = payload.get("params", {}).get("result", {}).get("value", {})
    context = payload.get("params", {}).get("result", {}).get("context", {})
    signature = value.get("signature")
    if not signature:
        return None
    return LogNotification(
        signature=signature,
        slot=int(context.get("slot", 0)),
        err=value.get("err"),
        logs=tuple(value.get("logs", ())),
    )


def subscription_message(program_id: str = PUMP_PROGRAM_ID) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "logsSubscribe",
        "params": [{"mentions": [program_id]}, {"commitment": "confirmed"}],
    }


def rpc_websocket_url() -> str:
    """Read-only RPC URL; never falls back to a signing endpoint."""
    return os.environ.get("SOLANA_WS_URL", "wss://api.mainnet-beta.solana.com")


def event_record(notification: LogNotification) -> dict[str, Any]:
    return {
        "signature": notification.signature,
        "slot": notification.slot,
        "err": notification.err,
        "logs": list(notification.logs),
        "program": PUMP_PROGRAM_ID,
    }


def json_line(record: dict[str, Any]) -> str:
    return json.dumps(record, separators=(",", ":"), sort_keys=True)
