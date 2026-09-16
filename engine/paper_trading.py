"""Guardian Paper Trading Engine.

A complete simulated trading engine that operates independently of live money.
Tracks positions, P&L, execution simulation, and risk monitoring.

Paper trading uses the SAME risk engine as live trading — the only difference
is that orders never reach an exchange. This ensures paper results are
meaningfully predictive of live behavior (within the limits of simulation).

Architecture:
- PaperTradingEngine composes RiskEngine + simulated order execution
- Every order goes through the full AUTHORIZED→VALIDATED→RISK→EXECUTE→RECONCILE→AUDIT pipeline
- Positions are tracked in-memory with full P&L accounting
- Execution simulation models slippage, partial fills, and rejection
- All state is queryable for monitoring and analysis
"""

from __future__ import annotations

import json
import logging
import random
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from engine.risk_engine import RiskEngine, RiskVerdict, Position

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Order and fill models
# ---------------------------------------------------------------------------

class OrderStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class Order:
    """A simulated order."""
    order_id: str
    symbol: str
    side: str  # "buy" or "sell"
    order_type: str  # "market" or "limit"
    quantity: float
    price: Optional[float]
    status: str = OrderStatus.PENDING
    strategy: str = "unknown"
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class Fill:
    """A simulated fill (execution)."""
    fill_id: str
    order_id: str
    symbol: str
    side: str
    fill_price: float
    fill_quantity: float
    fee_usdt: float
    slippage_bps: float
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ---------------------------------------------------------------------------
# Paper Trading Engine
# ---------------------------------------------------------------------------

class PaperTradingEngine:
    """Complete paper trading simulation.

    Every order follows:
        AUTHORIZED → DATA VALIDATED → RISK CHECK → EXECUTE → RECONCILE → AUDIT

    The engine composes RiskEngine for deterministic risk controls.
    Paper mode never contacts any exchange.
    """

    def __init__(
        self,
        seed_capital_usdt: float = 19.0,
        maker_fee_rate: float = 0.001,
        taker_fee_rate: float = 0.002,
        slippage_bps: float = 5.0,
        partial_fill_probability: float = 0.05,
        rejection_probability: float = 0.02,
    ) -> None:
        self._seed_capital = seed_capital_usdt
        self._maker_fee = maker_fee_rate
        self._taker_fee = taker_fee_rate
        self._slippage_bps = slippage_bps
        self._partial_fill_prob = partial_fill_probability
        self._rejection_prob = rejection_probability

        self._risk = RiskEngine(
            max_capital_usdt=seed_capital_usdt,
            max_position_size_usdt=seed_capital_usdt,
            max_total_exposure_usdt=seed_capital_usdt,
            seed_capital_usdt=seed_capital_usdt,
        )
        self._orders: Dict[str, Order] = {}
        self._fills: List[Fill] = []
        self._cash = seed_capital_usdt
        self._audit_log: List[Dict[str, Any]] = []
        self._position_counter = 0

    @property
    def risk_engine(self) -> RiskEngine:
        return self._risk

    @property
    def cash(self) -> float:
        return self._cash

    @property
    def portfolio_value(self) -> float:
        """Total portfolio value = cash + position values at entry."""
        position_value = sum(
            p.notional_usdt for p in self._risk.state.open_positions.values()
        )
        return self._cash + position_value

    def _record_audit(self, event: str, **details: Any) -> None:
        self._audit_log.append({
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **details,
        })

    def get_audit_log(self) -> List[Dict[str, Any]]:
        return list(self._audit_log)

    # -----------------------------------------------------------------------
    # Main entry: submit_order
    # -----------------------------------------------------------------------

    def submit_order(
        self,
        *,
        symbol: str,
        side: str,
        quantity: float,
        price: Optional[float] = None,
        order_type: str = "market",
        strategy: str = "unknown",
    ) -> Dict[str, Any]:
        """Submit an order through the full execution pipeline.

        Pipeline: AUTHORIZED → DATA VALIDATED → RISK CHECK → EXECUTE → RECONCILE → AUDIT

        Returns the complete order lifecycle result.
        """
        # Step 1: AUTHORIZED — create order
        order = Order(
            order_id=str(uuid.uuid4())[:12],
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            strategy=strategy,
        )
        self._orders[order.order_id] = order

        # Step 2: DATA VALIDATED — basic input validation
        if side not in ("buy", "sell"):
            return self._reject_order(order, "invalid side — must be 'buy' or 'sell'")
        if quantity <= 0:
            return self._reject_order(order, "quantity must be positive")
        if order_type == "limit" and (price is None or price <= 0):
            return self._reject_order(order, "limit order requires positive price")

        # Determine execution price
        exec_price = price if price and order_type == "limit" else self._estimate_market_price(symbol, side)

        # Step 3: RISK CHECK
        risk_verdict = self._risk.check_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=exec_price,
            strategy=strategy,
        )
        if not risk_verdict.approved:
            order.status = OrderStatus.REJECTED
            order.updated_at = datetime.now(timezone.utc).isoformat()
            self._record_audit(
                "order_risk_rejected",
                order_id=order.order_id,
                symbol=symbol,
                violations=[v.value for v in risk_verdict.violations],
            )
            return {
                "order_id": order.order_id,
                "status": OrderStatus.REJECTED,
                "reason": "risk_check_failed",
                "violations": [v.value for v in risk_verdict.violations],
                "details": risk_verdict.details,
            }

        order.status = OrderStatus.APPROVED

        # Step 4: EXECUTE — simulate fill
        fill = self._simulate_fill(order, exec_price)
        if fill is None:
            order.status = OrderStatus.REJECTED
            return {
                "order_id": order.order_id,
                "status": OrderStatus.REJECTED,
                "reason": "execution_failed",
            }

        order.status = OrderStatus.FILLED
        order.updated_at = datetime.now(timezone.utc).isoformat()
        self._fills.append(fill)

        # Step 5: RECONCILE — update positions and cash
        reconcile_result = self._reconcile(order, fill)

        # Step 6: AUDIT
        self._record_audit(
            "order_filled",
            order_id=order.order_id,
            symbol=symbol,
            side=side,
            fill_price=fill.fill_price,
            fill_quantity=fill.fill_quantity,
            fee_usdt=fill.fee_usdt,
            slippage_bps=fill.slippage_bps,
            pnl_usdt=reconcile_result.get("pnl_usdt", 0),
        )

        return {
            "order_id": order.order_id,
            "status": OrderStatus.FILLED,
            "symbol": symbol,
            "side": side,
            "quantity": fill.fill_quantity,
            "fill_price": fill.fill_price,
            "fee_usdt": fill.fee_usdt,
            "slippage_bps": fill.slippage_bps,
            "notional_usdt": fill.fill_price * fill.fill_quantity,
            "cash_after": round(self._cash, 6),
            "portfolio_value": round(self.portfolio_value, 6),
            "reconcile": reconcile_result,
        }

    def _reject_order(self, order: Order, reason: str) -> Dict[str, Any]:
        order.status = OrderStatus.REJECTED
        order.updated_at = datetime.now(timezone.utc).isoformat()
        self._record_audit(
            "order_rejected",
            order_id=order.order_id,
            symbol=order.symbol,
            reason=reason,
        )
        return {
            "order_id": order.order_id,
            "status": OrderStatus.REJECTED,
            "reason": reason,
        }

    def _estimate_market_price(self, symbol: str, side: str) -> float:
        """Estimate market price (simulation uses a fixed reference)."""
        # In a real implementation, this would use the last known price
        # from market data. For paper trading simulation, we use a
        # deterministic reference price based on symbol.
        base_prices = {
            "BTC_USDT": 60000.0,
            "ETH_USDT": 3000.0,
            "SOL_USDT": 150.0,
        }
        return base_prices.get(symbol, 100.0)

    def _simulate_fill(
        self, order: Order, exec_price: float
    ) -> Optional[Fill]:
        """Simulate an order fill with realistic behavior."""
        # Simulate rejection
        if random.random() < self._rejection_prob:
            return None

        # Simulate slippage
        slippage_mult = 1 + random.uniform(-0.001, 0.001)
        fill_price = exec_price * slippage_mult

        # Simulate partial fill
        fill_qty = order.quantity
        if random.random() < self._partial_fill_prob:
            fill_qty = order.quantity * random.uniform(0.5, 0.95)

        # Calculate fee
        fee = fill_qty * fill_price * self._taker_fee

        # Slippage in bps
        slippage_bps = abs(fill_price - exec_price) / exec_price * 10000

        return Fill(
            fill_id=str(uuid.uuid4())[:8],
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            fill_price=round(fill_price, 8),
            fill_quantity=round(fill_qty, 8),
            fee_usdt=round(fee, 6),
            slippage_bps=round(slippage_bps, 2),
        )

    def _reconcile(self, order: Order, fill: Fill) -> Dict[str, Any]:
        """Reconcile position and cash after fill."""
        notional = fill.fill_price * fill.fill_quantity
        pnl_usdt = 0.0

        if order.side == "buy":
            # Deduct cash
            self._cash -= (notional + fill.fee_usdt)

            # Check if this closes an existing short position (unlikely in spot)
            # For spot: open a long position
            pos = self._risk.open_position(
                symbol=order.symbol,
                side="buy",
                entry_price=fill.fill_price,
                quantity=fill.fill_quantity,
                strategy=order.strategy,
            )
        else:
            # Sell: add cash
            self._cash += (notional - fill.fee_usdt)

            # Try to close an existing position
            existing = [
                p
                for p in self._risk.state.open_positions.values()
                if p.symbol == order.symbol and p.side == "buy"
            ]
            if existing:
                # Close the first matching position
                close_result = self._risk.close_position(
                    existing[0].position_id, fill.fill_price
                )
                pnl_usdt = close_result.get("pnl_usdt", 0.0)
            else:
                # No position to close — this is a short (not allowed in spot-only)
                # In paper mode, we still track it but flag it
                logger.warning(
                    "PAPER: Sell order with no matching position — "
                    "spot-only policy means this should not happen in live mode"
                )

        return {
            "cash_after": round(self._cash, 6),
            "position_count": len(self._risk.state.open_positions),
            "pnl_usdt": round(pnl_usdt, 6),
        }

    # -----------------------------------------------------------------------
    # Query
    # -----------------------------------------------------------------------

    def get_positions(self) -> List[Dict[str, Any]]:
        """All open positions."""
        return [
            asdict(p) for p in self._risk.state.open_positions.values()
        ]

    def get_fills(self) -> List[Dict[str, Any]]:
        """All fills."""
        return [asdict(f) for f in self._fills]

    def get_order_history(self) -> List[Dict[str, Any]]:
        """All orders with their final status."""
        return [asdict(o) for o in self._orders.values()]

    def get_summary(self) -> Dict[str, Any]:
        """Complete paper trading summary."""
        return {
            "seed_capital_usdt": self._seed_capital,
            "cash": round(self._cash, 6),
            "portfolio_value": round(self.portfolio_value, 6),
            "unrealized_pnl": round(
                self.portfolio_value - self._seed_capital, 6
            ),
            "total_fills": len(self._fills),
            "total_orders": len(self._orders),
            "open_positions": len(self._risk.state.open_positions),
            "risk_status": self._risk.get_risk_status(),
            "exposure": self._risk.get_exposure(),
        }
