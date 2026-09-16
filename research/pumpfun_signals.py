"""Deterministic Pump.fun V2 signal interface; no transaction submission."""
from __future__ import annotations

from dataclasses import dataclass

from research.pumpfun_features import FeatureSnapshot


@dataclass(frozen=True)
class SignalConfig:
    min_flow_imbalance: float = 0.20
    min_velocity_per_min: float = 1.0
    min_expected_return: float = 0.0
    max_token_age_seconds: float = 900.0


@dataclass(frozen=True)
class TradeSignal:
    mint: str
    timestamp: int
    action: str
    score: float
    reasons: tuple[str, ...]


def generate_signal(
    snapshot: FeatureSnapshot,
    *,
    config: SignalConfig = SignalConfig(),
) -> TradeSignal:
    reasons: list[str] = []
    if snapshot.flow_imbalance >= config.min_flow_imbalance:
        reasons.append("positive_flow")
    if snapshot.tx_velocity_per_min >= config.min_velocity_per_min:
        reasons.append("velocity")
    expected = snapshot.expected_return_after_costs
    if expected is not None and expected >= config.min_expected_return:
        reasons.append("positive_expected_return")
    if snapshot.token_age_seconds is not None and snapshot.token_age_seconds <= config.max_token_age_seconds:
        reasons.append("age_ok")

    actionable = (
        "positive_flow" in reasons
        and "velocity" in reasons
        and "age_ok" in reasons
        and (expected is None or "positive_expected_return" in reasons)
    )
    score = max(0.0, snapshot.flow_imbalance)
    action = "BUY_PAPER" if actionable else "HOLD"
    return TradeSignal(snapshot.mint, snapshot.timestamp, action, score, tuple(reasons))
