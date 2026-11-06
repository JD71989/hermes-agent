"""Deterministic Pump.fun paper execution and P&L ledger; no live execution."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
from research.pumpfun_economics import PaperTrade, fee_breakdown
Side = Literal["BUY", "SELL"]

@dataclass(frozen=True)
class PaperFill:
    mint: str; timestamp: int; side: Side; quantity_tokens: float
    price_sol: float; notional_sol: float; total_cost_sol: float

@dataclass(frozen=True)
class Position:
    mint: str; quantity_tokens: float; average_entry_sol: float
    invested_sol: float; entry_timestamp: int

@dataclass(frozen=True)
class RealizedTrade:
    mint: str; entry_timestamp: int; exit_timestamp: int; quantity_tokens: float
    entry_price_sol: float; exit_price_sol: float; gross_pnl_sol: float
    costs_sol: float; net_pnl_sol: float

class PaperLedger:
    """Average-cost paper ledger. No wallet, signing, or live submission."""
    def __init__(self) -> None:
        self._positions: dict[str, Position] = {}
        self._fills: list[PaperFill] = []
        self._realized: list[RealizedTrade] = []

    @property
    def fills(self) -> tuple[PaperFill, ...]: return tuple(self._fills)
    @property
    def realized(self) -> tuple[RealizedTrade, ...]: return tuple(self._realized)
    def position(self, mint: str) -> Position | None: return self._positions.get(mint)

    def execute(self, *, mint: str, timestamp: int, side: Side, quantity_tokens: float,
                price_sol: float, phase: str, market_cap_sol: float,
                slippage_bps: float = 0.0, network_fee_sol: float = 0.0) -> PaperFill:
        if quantity_tokens <= 0 or price_sol <= 0:
            raise ValueError("quantity_tokens and price_sol must be positive")
        notional = quantity_tokens * price_sol
        costs = fee_breakdown(PaperTrade(side, notional, market_cap_sol, phase, slippage_bps, network_fee_sol))
        fill = PaperFill(mint, timestamp, side, quantity_tokens, price_sol, notional, costs.total_cost_sol)
        if side == "BUY": self._buy(fill)
        else: self._sell(fill)
        self._fills.append(fill)
        return fill

    def _buy(self, fill: PaperFill) -> None:
        current = self._positions.get(fill.mint)
        if current is None:
            invested = fill.notional_sol + fill.total_cost_sol
            self._positions[fill.mint] = Position(fill.mint, fill.quantity_tokens,
                                                  invested / fill.quantity_tokens, invested, fill.timestamp)
            return
        new_qty = current.quantity_tokens + fill.quantity_tokens
        invested = current.invested_sol + fill.notional_sol + fill.total_cost_sol
        self._positions[fill.mint] = Position(fill.mint, new_qty, invested / new_qty,
                                              invested, current.entry_timestamp)

    def _sell(self, fill: PaperFill) -> None:
        current = self._positions.get(fill.mint)
        if current is None or fill.quantity_tokens > current.quantity_tokens:
            raise ValueError("insufficient paper position")
        gross = fill.notional_sol - current.average_entry_sol * fill.quantity_tokens
        entry_cost_total = max(0.0, current.invested_sol - current.average_entry_sol * current.quantity_tokens)
        entry_cost = entry_cost_total * fill.quantity_tokens / current.quantity_tokens
        exit_cost = fill.total_cost_sol
        net = gross - entry_cost - exit_cost
        self._realized.append(RealizedTrade(fill.mint, current.entry_timestamp, fill.timestamp,
                                            fill.quantity_tokens, current.average_entry_sol, fill.price_sol,
                                            gross, entry_cost + exit_cost, net))
        remaining = current.quantity_tokens - fill.quantity_tokens
        if remaining <= 0:
            self._positions.pop(fill.mint, None)
        else:
            remaining_invested = current.invested_sol * remaining / current.quantity_tokens
            self._positions[fill.mint] = Position(fill.mint, remaining, current.average_entry_sol,
                                                  remaining_invested, current.entry_timestamp)

# Live transaction submission is intentionally absent from this module.
