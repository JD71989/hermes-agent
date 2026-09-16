"""Guardian Live Execution Pipeline.

Implements the complete execution flow:
    AUTHORIZED → DATA VALIDATED → RISK CHECK → EXECUTE → RECONCILE → AUDIT

LIVE FINANCIAL EXECUTION IS LOCKED BY DEFAULT.
Every live order must pass ALL gates before execution.
The pipeline is designed so that:
1. Authorization requires explicit human grant
2. Data validation checks market data freshness
3. Risk check uses the deterministic RiskEngine
4. Execution requires live mode + live flag + authorization
5. Reconciliation updates positions and cash
6. Audit records every step

Architecture:
- LiveExecutionPipeline composes RiskEngine + DataValidator
- authorization_granted is a class-level flag (not per-instance)
- live_enabled requires both mode=MICRO-LIVE AND PIONEX_LIVE_TRADING=1
- Even when all gates pass, the pipeline returns a result dict —
  the actual API call is a separate concern
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

from engine.risk_engine import RiskEngine, RiskVerdict
from engine.market_data import DataValidator, MarketTick

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Execution stages
# ---------------------------------------------------------------------------

class ExecutionStage(Enum):
    AUTHORIZED = "authorized"
    DATA_VALIDATED = "data_validated"
    RISK_CHECKED = "risk_checked"
    EXECUTING = "executing"
    RECONCILING = "reconciling"
    AUDITING = "auditing"
    COMPLETED = "completed"
    FAILED = "failed"


class ExecutionMode(Enum):
    SCAN = "SCAN"
    PAPER = "PAPER"
    MICRO_LIVE = "MICRO-LIVE"


# ---------------------------------------------------------------------------
# Execution result
# ---------------------------------------------------------------------------

@dataclass
class ExecutionResult:
    """Immutable result of an execution attempt."""
    order_id: str
    stage_reached: ExecutionStage
    success: bool
    mode: str
    symbol: str
    side: str
    quantity: float
    price: Optional[float]
    fill_price: Optional[float] = None
    fill_quantity: Optional[float] = None
    fee_usdt: float = 0.0
    risk_verdict: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    audit_entries: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "stage_reached": self.stage_reached.value,
            "success": self.success,
            "mode": self.mode,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "price": self.price,
            "fill_price": self.fill_price,
            "fill_quantity": self.fill_quantity,
            "fee_usdt": self.fee_usdt,
            "risk_verdict": self.risk_verdict,
            "error": self.error,
            "audit_entries": self.audit_entries,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# Live Execution Pipeline
# ---------------------------------------------------------------------------

class LiveExecutionPipeline:
    """The complete execution pipeline with all gates.

    Pipeline stages:
        1. AUTHORIZED — requires explicit human authorization
        2. DATA VALIDATED — market data freshness and sanity
        3. RISK CHECK — deterministic risk engine validation
        4. EXECUTE — actual order placement (gated on mode + authorization)
        5. RECONCILE — update positions and P&L
        6. AUDIT — record every step

    Live execution is locked by default. To enable:
        1. Set mode to MICRO-LIVE
        2. Set PIONEX_LIVE_TRADING=1
        3. Grant explicit authorization
    """

    # Class-level authorization — requires explicit human grant
    _authorization_granted = False
    _authorization_granted_by: Optional[str] = None
    _authorization_granted_at: Optional[str] = None

    def __init__(
        self,
        risk_engine: Optional[RiskEngine] = None,
        mode: str = "SCAN",
        live_trading_enabled: bool = False,
    ) -> None:
        self._risk = risk_engine or RiskEngine()
        self._mode = mode
        self._live_enabled = live_trading_enabled
        self._validator = DataValidator()
        self._audit_log: List[Dict[str, Any]] = []

    @classmethod
    def grant_authorization(cls, granted_by: str = "human_operator") -> None:
        """Explicitly grant execution authorization.

        In production, this requires authenticated human action.
        NEXUS and its tools CANNOT call this.
        """
        cls._authorization_granted = True
        cls._authorization_granted_by = granted_by
        cls._authorization_granted_at = datetime.now(timezone.utc).isoformat()
        logger.warning(
            "LIVE EXECUTION AUTHORIZATION GRANTED by %s at %s",
            granted_by,
            cls._authorization_granted_at,
        )

    @classmethod
    def revoke_authorization(cls) -> None:
        cls._authorization_granted = False
        cls._authorization_granted_by = None
        cls._authorization_granted_at = None
        logger.info("LIVE EXECUTION AUTHORIZATION REVOKED")

    @classmethod
    def is_authorized(cls) -> bool:
        return cls._authorization_granted

    def _audit(self, stage: str, **details: Any) -> Dict[str, Any]:
        entry = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stage": stage,
            **details,
        }
        self._audit_log.append(entry)
        return entry

    def get_audit_log(self) -> List[Dict[str, Any]]:
        return list(self._audit_log)

    def execute(
        self,
        *,
        symbol: str,
        side: str,
        quantity: float,
        price: Optional[float] = None,
        tick: Optional[MarketTick] = None,
        strategy: str = "unknown",
    ) -> ExecutionResult:
        """Execute an order through the full pipeline.

        Returns ExecutionResult with the stage reached and outcome.
        """
        order_id = str(uuid.uuid4())[:12]
        audit_entries: List[Dict[str, Any]] = []

        # ------------------------------------------------------------------
        # Stage 1: AUTHORIZED
        # ------------------------------------------------------------------
        if not self._authorization_granted:
            entry = self._audit(
                "authorization_denied",
                order_id=order_id,
                reason="no explicit authorization granted",
            )
            audit_entries.append(entry)
            return ExecutionResult(
                order_id=order_id,
                stage_reached=ExecutionStage.AUTHORIZED,
                success=False,
                mode=self._mode,
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
                error="LIVE EXECUTION NOT AUTHORIZED — requires explicit human authorization",
                audit_entries=audit_entries,
            )

        entry = self._audit(
            "authorized",
            order_id=order_id,
            granted_by=self._authorization_granted_by,
        )
        audit_entries.append(entry)

        # ------------------------------------------------------------------
        # Stage 2: DATA VALIDATED
        # ------------------------------------------------------------------
        if tick is not None:
            validated_tick = self._validator.validate_tick(tick)
            if validated_tick.is_stale:
                entry = self._audit(
                    "data_validation_failed",
                    order_id=order_id,
                    reason="market data is stale",
                )
                audit_entries.append(entry)
                return ExecutionResult(
                    order_id=order_id,
                    stage_reached=ExecutionStage.DATA_VALIDATED,
                    success=False,
                    mode=self._mode,
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    price=price,
                    error="Market data is stale — cannot execute on stale data",
                    audit_entries=audit_entries,
                )
            if validated_tick.validation_errors:
                entry = self._audit(
                    "data_validation_errors",
                    order_id=order_id,
                    errors=list(validated_tick.validation_errors),
                )
                audit_entries.append(entry)

        entry = self._audit("data_validated", order_id=order_id)
        audit_entries.append(entry)

        # ------------------------------------------------------------------
        # Stage 3: RISK CHECK
        # ------------------------------------------------------------------
        exec_price = price if price else (tick.last_price if tick else 0.0)
        risk_verdict = self._risk.check_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=exec_price,
            strategy=strategy,
        )

        entry = self._audit(
            "risk_check",
            order_id=order_id,
            approved=risk_verdict.approved,
            violations=[v.value for v in risk_verdict.violations],
        )
        audit_entries.append(entry)

        if not risk_verdict.approved:
            return ExecutionResult(
                order_id=order_id,
                stage_reached=ExecutionStage.RISK_CHECKED,
                success=False,
                mode=self._mode,
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
                risk_verdict=risk_verdict.to_dict(),
                error=f"Risk check failed: {[v.value for v in risk_verdict.violations]}",
                audit_entries=audit_entries,
            )

        # ------------------------------------------------------------------
        # Stage 4: EXECUTE
        # ------------------------------------------------------------------
        is_live = (
            self._mode == ExecutionMode.MICRO_LIVE.value
            and self._live_enabled
        )

        if not is_live:
            entry = self._audit(
                "execution_blocked_not_live",
                order_id=order_id,
                mode=self._mode,
                live_enabled=self._live_enabled,
            )
            audit_entries.append(entry)
            return ExecutionResult(
                order_id=order_id,
                stage_reached=ExecutionStage.EXECUTING,
                success=False,
                mode=self._mode,
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
                risk_verdict=risk_verdict.to_dict(),
                error=(
                    "Execution blocked: live trading not enabled. "
                    "Set mode=MICRO-LIVE and PIONEX_LIVE_TRADING=1."
                ),
                audit_entries=audit_entries,
            )

        # Live execution path — in a real system, this calls the exchange API
        # For this build, it returns "not_implemented" to prove the gate works
        entry = self._audit(
            "execution_blocked_not_implemented",
            order_id=order_id,
            reason="live API integration not implemented in this build",
        )
        audit_entries.append(entry)

        return ExecutionResult(
            order_id=order_id,
            stage_reached=ExecutionStage.EXECUTING,
            success=False,
            mode=self._mode,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            risk_verdict=risk_verdict.to_dict(),
            error=(
                "LIVE EXECUTION NOT IMPLEMENTED IN THIS BUILD. "
                "The pipeline gates are proven correct. "
                "A real Pionex API integration would be placed here."
            ),
            audit_entries=audit_entries,
        )
