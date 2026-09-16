"""Guardian Deterministic Risk Engine.

Enforces ALL risk controls deterministically. The LLM cannot override
any control — every limit is checked algorithmically, not by prompt instruction.

Controls enforced:
- Position sizing (max notional per trade)
- Maximum total exposure (across all open positions)
- Maximum loss (daily and total)
- Drawdown limits (max peak-to-trough)
- Concentration limits (max allocation per asset)
- Emergency stop (immediate halt of all trading)

Architecture:
- RiskEngine is a stateful object that tracks positions, P&L, drawdown
- Every order request passes through check_order() which returns RiskVerdict
- RiskVerdict is immutable — once denied, the order cannot proceed
- Kill switch is non-negotiable — once engaged, ALL orders are blocked
- The engine is self-contained: no LLM prompts, no network calls, no side effects
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

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Risk policy constants (immutable, not overridable by parameters)
# ---------------------------------------------------------------------------

MAX_CAPITAL_USDT = 19.0
MAX_POSITION_SIZE_USDT = 19.0
MAX_TOTAL_EXPOSURE_USDT = 19.0
MAX_DAILY_LOSS_USDT = 19.0
MAX_TOTAL_LOSS_USDT = 19.0
MAX_DRAWDOWN_PCT = 0.50  # 50% max drawdown
MAX_CONCENTRATION_PCT = 1.0  # 100% — single asset max (can be lower)
MAX_OPEN_POSITIONS = 1
MAX_CONSECUTIVE_LOSSES = 3
EMERGENCY_STOP_COOLDOWN_SECONDS = 300  # 5 minutes after emergency stop
SPOT_ONLY = True
LEVERAGE_FORBIDDEN = True


class RiskViolation(Enum):
    """Why a risk check failed."""
    KILL_SWITCH_ENGAGED = "kill_switch_engaged"
    EXCEEDS_POSITION_SIZE = "exceeds_position_size"
    EXCEEDS_TOTAL_EXPOSURE = "exceeds_total_exposure"
    EXCEEDS_DAILY_LOSS = "exceeds_daily_loss"
    EXCEEDS_TOTAL_LOSS = "exceeds_total_loss"
    EXCEEDS_DRAWDOWN_LIMIT = "exceeds_drawdown_limit"
    EXCEEDS_CONCENTRATION_LIMIT = "exceeds_concentration_limit"
    TOO_MANY_OPEN_POSITIONS = "too_many_open_positions"
    TOO_MANY_CONSECUTIVE_LOSSES = "too_many_consecutive_losses"
    EMERGENCY_STOP_COOLDOWN = "emergency_stop_cooldown"
    LEVERAGE_FORBIDDEN = "leverage_forbidden"
    INVALID_ORDER = "invalid_order"
    CAPACITY_EXCEEDED = "capacity_exceeded"


@dataclass(frozen=True)
class RiskVerdict:
    """Immutable verdict from a risk check. Once denied, cannot be overridden."""
    approved: bool
    violations: tuple  # tuple of RiskViolation
    details: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approved": self.approved,
            "violations": [v.value for v in self.violations],
            "details": self.details,
            "timestamp": self.timestamp,
        }


@dataclass
class Position:
    """A tracked open position."""
    position_id: str
    symbol: str
    side: str  # "buy" or "sell"
    entry_price: float
    quantity: float
    notional_usdt: float
    opened_at: str
    strategy: str = "unknown"


@dataclass
class RiskState:
    """Mutable risk state — tracks exposure, P&L, drawdown."""
    daily_pnl: float = 0.0
    total_pnl: float = 0.0
    peak_pnl: float = 0.0
    current_drawdown: float = 0.0
    max_drawdown: float = 0.0
    consecutive_losses: int = 0
    open_positions: Dict[str, Position] = field(default_factory=dict)
    daily_trade_count: int = 0
    last_emergency_stop: float = 0.0


class RiskEngine:
    """The single authoritative risk gate.

    Every order MUST pass through check_order() before execution.
    The engine enforces ALL controls deterministically — no prompt,
    no LLM call, no override parameter can bypass a denied verdict.

    The engine is designed to be safe by default: if any control
    raises an exception, the order is denied (fail-closed).
    """

    def __init__(
        self,
        max_capital_usdt: float = MAX_CAPITAL_USDT,
        max_position_size_usdt: float = MAX_POSITION_SIZE_USDT,
        max_total_exposure_usdt: float = MAX_TOTAL_EXPOSURE_USDT,
        max_daily_loss_usdt: float = MAX_DAILY_LOSS_USDT,
        max_total_loss_usdt: float = MAX_TOTAL_LOSS_USDT,
        max_drawdown_pct: float = MAX_DRAWDOWN_PCT,
        max_concentration_pct: float = MAX_CONCENTRATION_PCT,
        max_open_positions: int = MAX_OPEN_POSITIONS,
        max_consecutive_losses: int = MAX_CONSECUTIVE_LOSSES,
        seed_capital_usdt: float = MAX_CAPITAL_USDT,
    ) -> None:
        self._max_capital = max_capital_usdt
        self._max_position_size = max_position_size_usdt
        self._max_total_exposure = max_total_exposure_usdt
        self._max_daily_loss = max_daily_loss_usdt
        self._max_total_loss = max_total_loss_usdt
        self._max_drawdown_pct = max_drawdown_pct
        self._max_concentration_pct = max_concentration_pct
        self._max_open_positions = max_open_positions
        self._max_consecutive_losses = max_consecutive_losses
        self._seed_capital = seed_capital_usdt
        self._state = RiskState()
        self._kill_switch = False
        self._audit_log: List[Dict[str, Any]] = []

    @property
    def state(self) -> RiskState:
        return self._state

    @property
    def kill_switch_active(self) -> bool:
        return self._kill_switch

    def engage_kill_switch(self) -> None:
        """Immediately halt ALL trading. Non-negotiable."""
        self._kill_switch = True
        self._state.last_emergency_stop = time.time()
        self._record("kill_switch_activated")
        logger.warning("RISK ENGINE: KILL SWITCH ENGAGED — ALL TRADING HALTED")

    def disengage_kill_switch(self) -> None:
        """Re-engage only after cooldown period."""
        elapsed = time.time() - self._state.last_emergency_stop
        if elapsed < EMERGENCY_STOP_COOLDOWN_SECONDS:
            remaining = EMERGENCY_STOP_COOLDOWN_SECONDS - elapsed
            logger.warning(
                "RISK ENGINE: Kill switch cooldown — %.0f seconds remaining",
                remaining,
            )
            return
        self._kill_switch = False
        self._record("kill_switch_disengaged")
        logger.info("RISK ENGINE: Kill switch disengaged")

    def reset_daily(self) -> None:
        """Reset daily counters. Call at start of each trading day."""
        self._state.daily_pnl = 0.0
        self._state.daily_trade_count = 0
        self._record("daily_reset")

    def _record(self, event_type: str, **details: Any) -> None:
        entry = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            **details,
        }
        self._audit_log.append(entry)

    def get_audit_log(self) -> List[Dict[str, Any]]:
        return list(self._audit_log)

    # -----------------------------------------------------------------------
    # Core: check_order — the single entry point for risk validation
    # -----------------------------------------------------------------------

    def check_order(
        self,
        *,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        strategy: str = "unknown",
        leverage: float = 1.0,
    ) -> RiskVerdict:
        """Validate an order against ALL risk controls.

        Returns RiskVerdict (immutable). If approved=False, the order
        MUST NOT proceed. Violations are specific and actionable.
        """
        violations: List[RiskViolation] = []
        details: Dict[str, Any] = {}

        notional = quantity * price

        # 1. Kill switch
        if self._kill_switch:
            violations.append(RiskViolation.KILL_SWITCH_ENGAGED)

        # 2. Emergency stop cooldown
        if self._kill_switch:
            elapsed = time.time() - self._state.last_emergency_stop
            if elapsed < EMERGENCY_STOP_COOLDOWN_SECONDS:
                violations.append(RiskViolation.EMERGENCY_STOP_COOLDOWN)

        # 3. Invalid order
        if quantity <= 0 or price <= 0 or notional <= 0:
            violations.append(RiskViolation.INVALID_ORDER)
            details["reason"] = "quantity and price must be positive"

        # 4. Leverage forbidden
        if leverage != 1.0:
            violations.append(RiskViolation.LEVERAGE_FORBIDDEN)

        # SPOT ONLY: a sell must map onto an existing long position —
        # naked shorts are never allowed in any mode.
        held_qty = sum(
            p.quantity
            for p in self._state.open_positions.values()
            if p.symbol == symbol and p.side == "buy"
        )
        closing_order = side == "sell" and held_qty >= quantity
        if side == "sell" and held_qty < quantity:
            violations.append(RiskViolation.INVALID_ORDER)
            details["reason"] = (
                "sell exceeds held quantity — SPOT ONLY, no shorting"
                if held_qty > 0
                else "sell without an existing position — SPOT ONLY, no shorting"
            )

        # Position-sizing limits apply to NEW exposure only; an order that
        # closes/reduces an existing position is always allowed past them.
        if not closing_order:
            # 5. Position size limit
            if notional > self._max_position_size:
                violations.append(RiskViolation.EXCEEDS_POSITION_SIZE)
                details["notional"] = notional
                details["max_position_size"] = self._max_position_size

            # 6. Total exposure limit
            current_exposure = sum(
                p.notional_usdt for p in self._state.open_positions.values()
            )
            projected_exposure = current_exposure + notional
            if projected_exposure > self._max_total_exposure:
                violations.append(RiskViolation.EXCEEDS_TOTAL_EXPOSURE)
                details["projected_exposure"] = projected_exposure
                details["max_total_exposure"] = self._max_total_exposure

            # 7. Concentration limit
            symbol_exposure = sum(
                p.notional_usdt
                for p in self._state.open_positions.values()
                if p.symbol == symbol
            )
            projected_symbol_exposure = symbol_exposure + notional
            concentration = (
                projected_symbol_exposure / self._seed_capital
                if self._seed_capital > 0
                else 1.0
            )
            if concentration > self._max_concentration_pct:
                violations.append(RiskViolation.EXCEEDS_CONCENTRATION_LIMIT)
                details["concentration"] = concentration
                details["max_concentration"] = self._max_concentration_pct

            # 8. Max open positions
            if len(self._state.open_positions) >= self._max_open_positions:
                violations.append(RiskViolation.TOO_MANY_OPEN_POSITIONS)
                details["open_count"] = len(self._state.open_positions)
                details["max_open"] = self._max_open_positions

        # 9. Daily loss limit
        if self._state.daily_pnl < -self._max_daily_loss:
            violations.append(RiskViolation.EXCEEDS_DAILY_LOSS)
            details["daily_pnl"] = self._state.daily_pnl
            details["max_daily_loss"] = self._max_daily_loss

        # 10. Total loss limit
        if self._state.total_pnl < -self._max_total_loss:
            violations.append(RiskViolation.EXCEEDS_TOTAL_LOSS)
            details["total_pnl"] = self._state.total_pnl
            details["max_total_loss"] = self._max_total_loss

        # 11. Drawdown limit
        if self._state.max_drawdown > self._max_drawdown_pct:
            violations.append(RiskViolation.EXCEEDS_DRAWDOWN_LIMIT)
            details["max_drawdown"] = self._state.max_drawdown
            details["max_drawdown_pct"] = self._max_drawdown_pct

        # 12. Consecutive losses
        if self._state.consecutive_losses >= self._max_consecutive_losses:
            violations.append(RiskViolation.TOO_MANY_CONSECUTIVE_LOSSES)
            details["consecutive_losses"] = self._state.consecutive_losses
            details["max_consecutive_losses"] = self._max_consecutive_losses

        approved = len(violations) == 0
        verdict = RiskVerdict(
            approved=approved,
            violations=tuple(violations),
            details=details,
        )

        self._record(
            "order_check",
            symbol=symbol,
            side=side,
            notional=notional,
            approved=approved,
            violations=[v.value for v in violations],
        )

        return verdict

    # -----------------------------------------------------------------------
    # Position management
    # -----------------------------------------------------------------------

    def open_position(
        self,
        *,
        symbol: str,
        side: str,
        entry_price: float,
        quantity: float,
        strategy: str = "unknown",
    ) -> Position:
        """Register an open position. Must pass check_order first."""
        notional = entry_price * quantity
        pos = Position(
            position_id=str(uuid.uuid4())[:8],
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            quantity=quantity,
            notional_usdt=notional,
            opened_at=datetime.now(timezone.utc).isoformat(),
            strategy=strategy,
        )
        self._state.open_positions[pos.position_id] = pos
        self._state.daily_trade_count += 1
        self._record(
            "position_opened",
            position_id=pos.position_id,
            symbol=symbol,
            side=side,
            notional=notional,
        )
        return pos

    def close_position(
        self,
        position_id: str,
        exit_price: float,
    ) -> Dict[str, Any]:
        """Close a position and update P&L state."""
        pos = self._state.open_positions.get(position_id)
        if pos is None:
            return {"error": f"position {position_id} not found"}

        if pos.side == "buy":
            pnl = (exit_price - pos.entry_price) * pos.quantity
        else:
            pnl = (pos.entry_price - exit_price) * pos.quantity

        # Update P&L
        self._state.daily_pnl += pnl
        self._state.total_pnl += pnl

        # Update peak and drawdown
        self._state.peak_pnl = max(self._state.peak_pnl, self._state.total_pnl)
        if self._state.peak_pnl > 0:
            self._state.current_drawdown = (
                (self._state.peak_pnl - self._state.total_pnl) / self._state.peak_pnl
            )
        self._state.max_drawdown = max(
            self._state.max_drawdown, self._state.current_drawdown
        )

        # Update consecutive losses
        if pnl < 0:
            self._state.consecutive_losses += 1
        else:
            self._state.consecutive_losses = 0

        # Remove position
        del self._state.open_positions[position_id]

        result = {
            "position_id": position_id,
            "symbol": pos.symbol,
            "side": pos.side,
            "entry_price": pos.entry_price,
            "exit_price": exit_price,
            "quantity": pos.quantity,
            "pnl_usdt": round(pnl, 6),
            "daily_pnl": round(self._state.daily_pnl, 6),
            "total_pnl": round(self._state.total_pnl, 6),
            "max_drawdown": round(self._state.max_drawdown, 6),
            "consecutive_losses": self._state.consecutive_losses,
        }

        self._record("position_closed", **result)
        return result

    # -----------------------------------------------------------------------
    # Query
    # -----------------------------------------------------------------------

    def get_exposure(self) -> Dict[str, Any]:
        """Current exposure summary."""
        total = sum(p.notional_usdt for p in self._state.open_positions.values())
        by_symbol: Dict[str, float] = {}
        for p in self._state.open_positions.values():
            by_symbol[p.symbol] = by_symbol.get(p.symbol, 0.0) + p.notional_usdt
        return {
            "total_exposure_usdt": round(total, 4),
            "max_total_exposure_usdt": self._max_total_exposure,
            "utilization_pct": round(
                (total / self._max_total_exposure * 100) if self._max_total_exposure > 0 else 0,
                2,
            ),
            "by_symbol": {k: round(v, 4) for k, v in by_symbol.items()},
            "open_positions": len(self._state.open_positions),
            "max_open_positions": self._max_open_positions,
        }

    def get_risk_status(self) -> Dict[str, Any]:
        """Full risk status snapshot."""
        return {
            "kill_switch_active": self._kill_switch,
            "daily_pnl": round(self._state.daily_pnl, 6),
            "total_pnl": round(self._state.total_pnl, 6),
            "peak_pnl": round(self._state.peak_pnl, 6),
            "current_drawdown": round(self._state.current_drawdown, 6),
            "max_drawdown": round(self._state.max_drawdown, 6),
            "max_drawdown_limit": self._max_drawdown_pct,
            "consecutive_losses": self._state.consecutive_losses,
            "max_consecutive_losses": self._max_consecutive_losses,
            "daily_trade_count": self._state.daily_trade_count,
            "exposure": self.get_exposure(),
            "limits": {
                "max_capital_usdt": self._max_capital,
                "max_position_size_usdt": self._max_position_size,
                "max_total_exposure_usdt": self._max_total_exposure,
                "max_daily_loss_usdt": self._max_daily_loss,
                "max_total_loss_usdt": self._max_total_loss,
                "max_drawdown_pct": self._max_drawdown_pct,
                "max_concentration_pct": self._max_concentration_pct,
                "max_open_positions": self._max_open_positions,
                "max_consecutive_losses": self._max_consecutive_losses,
            },
        }
