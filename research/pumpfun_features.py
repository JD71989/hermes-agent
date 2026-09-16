"""Deterministic, timestamp-safe Pump.fun V2 feature extraction."""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean

from research.pumpfun_engine import MarketPhase, TokenEvent


@dataclass(frozen=True)
class FeatureSnapshot:
    mint: str
    timestamp: int
    token_age_seconds: float | None
    buy_volume_sol: float
    sell_volume_sol: float
    flow_imbalance: float
    tx_velocity_per_min: float
    volume_acceleration: float
    liquidity_sol: float | None
    market_cap_sol: float | None
    market_cap_velocity: float | None
    holder_concentration_pct: float | None
    creator_share_pct: float | None
    bonding_curve_position_pct: float | None
    graduation_proximity_pct: float | None
    post_graduation: bool
    expected_return_after_costs: float | None


@dataclass(frozen=True)
class FeatureConfig:
    velocity_window_seconds: int = 60
    acceleration_window_seconds: int = 120
    graduation_market_cap_sol: float = 79.0
    expected_exit_price_sol: float | None = None
    estimated_slippage_bps: float = 0.0
    estimated_fee_bps: float = 125.0


def _signed_volume(event: TokenEvent) -> float:
    return event.sol_delta


def _flow(events: list[TokenEvent]) -> tuple[float, float, float]:
    buys = sum(max(_signed_volume(e), 0.0) for e in events)
    sells = sum(max(-_signed_volume(e), 0.0) for e in events)
    total = buys + sells
    imbalance = (buys - sells) / total if total else 0.0
    return buys, sells, imbalance


def _velocity(events: list[TokenEvent], now: int, window: int) -> float:
    cutoff = now - window
    return sum(1 for e in events if cutoff <= e.timestamp <= now) / (window / 60.0)


def _volume_acceleration(events: list[TokenEvent], now: int, window: int) -> float:
    if window <= 0:
        return 0.0
    midpoint = now - window
    recent_start = now - window // 2
    recent = [e for e in events if recent_start <= e.timestamp <= now]
    prior = [e for e in events if midpoint <= e.timestamp < recent_start]
    recent_volume = sum(abs(e.sol_delta) for e in recent)
    prior_volume = sum(abs(e.sol_delta) for e in prior)
    if prior_volume == 0:
        return float("inf") if recent_volume else 0.0
    return recent_volume / prior_volume - 1.0


def _latest(events: list[TokenEvent], attr: str):
    values = [e for e in events if getattr(e, attr) is not None]
    return getattr(max(values, key=lambda e: e.timestamp), attr) if values else None


def _market_cap_velocity(events: list[TokenEvent]) -> float | None:
    points = [e for e in events if e.market_cap_sol is not None]
    if len(points) < 2:
        return None
    a, b = sorted(points, key=lambda e: e.timestamp)[-2:]
    dt = b.timestamp - a.timestamp
    return (b.market_cap_sol - a.market_cap_sol) / dt if dt > 0 else 0.0


def _expected_return(event: TokenEvent, config: FeatureConfig) -> float | None:
    if event.price_sol is None or config.expected_exit_price_sol is None or event.price_sol <= 0:
        return None
    gross = config.expected_exit_price_sol / event.price_sol - 1.0
    costs = (config.estimated_slippage_bps + config.estimated_fee_bps) / 10_000
    return gross - costs


def build_feature_snapshot(
    events: list[TokenEvent],
    *,
    now: int | None = None,
    config: FeatureConfig = FeatureConfig(),
) -> FeatureSnapshot:
    """Build from events whose timestamps are <= now; future events are ignored."""
    if not events:
        raise ValueError("events must not be empty")
    cutoff = max(e.timestamp for e in events) if now is None else now
    observed = [e for e in events if e.timestamp <= cutoff]
    if not observed:
        raise ValueError("no events are available at the requested timestamp")
    ordered = sorted(observed, key=lambda e: (e.timestamp, e.slot, e.signature))
    current = ordered[-1]
    mint = current.mint
    token_events = [e for e in ordered if e.mint == mint]
    creation = min(token_events, key=lambda e: e.timestamp)
    age = max(0, cutoff - creation.timestamp)
    buy, sell, imbalance = _flow(token_events)
    latest_liquidity = _latest(token_events, "liquidity_sol")
    latest_mcap = _latest(token_events, "market_cap_sol")
    curve = min(100.0, max(0.0, latest_mcap / config.graduation_market_cap_sol * 100.0)) if latest_mcap is not None else None
    phase_graduated = current.phase == MarketPhase.GRADUATED
    proximity = 100.0 - curve if curve is not None and not phase_graduated else 0.0 if phase_graduated else None
    creator_share = None
    holder_concentration = None
    return FeatureSnapshot(
        mint=mint,
        timestamp=cutoff,
        token_age_seconds=float(age),
        buy_volume_sol=buy,
        sell_volume_sol=sell,
        flow_imbalance=imbalance,
        tx_velocity_per_min=_velocity(token_events, cutoff, config.velocity_window_seconds),
        volume_acceleration=_volume_acceleration(token_events, cutoff, config.acceleration_window_seconds),
        liquidity_sol=latest_liquidity,
        market_cap_sol=latest_mcap,
        market_cap_velocity=_market_cap_velocity(token_events),
        holder_concentration_pct=holder_concentration,
        creator_share_pct=creator_share,
        bonding_curve_position_pct=curve,
        graduation_proximity_pct=proximity,
        post_graduation=phase_graduated,
        expected_return_after_costs=_expected_return(current, config),
    )


@dataclass(frozen=True)
class FeatureInput:
    events: tuple[TokenEvent, ...]
    holder_concentration_pct: float | None = None
    creator_share_pct: float | None = None


def build_feature_snapshot_v2(
    data: FeatureInput,
    *,
    now: int | None = None,
    config: FeatureConfig = FeatureConfig(),
) -> FeatureSnapshot:
    """V2 facade allowing holder/creator observations to enter separately."""
    snap = build_feature_snapshot(list(data.events), now=now, config=config)
    return FeatureSnapshot(
        **{**snap.__dict__,
           "holder_concentration_pct": data.holder_concentration_pct,
           "creator_share_pct": data.creator_share_pct}
    )
