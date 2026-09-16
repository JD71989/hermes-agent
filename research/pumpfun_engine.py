"""Guardian Pump.fun Engine V1: read-only event model and deterministic risk gate.

Market-specific module. Live execution is deliberately absent in V1.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MarketPhase(str, Enum):
    BONDING_CURVE = "bonding_curve"
    GRADUATED = "graduated"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TokenEvent:
    signature: str
    slot: int
    timestamp: int
    mint: str
    event_type: str
    sol_delta: float = 0.0
    token_delta: float = 0.0
    price_sol: float | None = None
    liquidity_sol: float | None = None
    market_cap_sol: float | None = None
    phase: MarketPhase = MarketPhase.UNKNOWN
    creator: str | None = None


@dataclass(frozen=True)
class RiskLimits:
    max_position_sol: float = 0.25
    max_slippage_bps: float = 300.0
    max_token_age_seconds: int = 900
    min_liquidity_sol: float = 5.0
    max_creator_share_pct: float = 35.0


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reasons: tuple[str, ...]


def risk_gate(
    *,
    token_age_seconds: int,
    liquidity_sol: float,
    creator_share_pct: float,
    estimated_slippage_bps: float,
    requested_position_sol: float,
    limits: RiskLimits = RiskLimits(),
) -> RiskDecision:
    reasons: list[str] = []
    if requested_position_sol > limits.max_position_sol:
        reasons.append("position_size_limit")
    if estimated_slippage_bps > limits.max_slippage_bps:
        reasons.append("slippage_limit")
    if token_age_seconds > limits.max_token_age_seconds:
        reasons.append("token_age_limit")
    if liquidity_sol < limits.min_liquidity_sol:
        reasons.append("liquidity_floor")
    if creator_share_pct > limits.max_creator_share_pct:
        reasons.append("creator_concentration")
    return RiskDecision(not reasons, tuple(reasons))
