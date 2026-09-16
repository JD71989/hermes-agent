"""Chronological Pump.fun replay for research and paper signals.

The replay engine never exposes events newer than the current event timestamp.
It records the feature snapshot and paper signal observed at each step.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from research.pumpfun_engine import TokenEvent
from research.pumpfun_features import FeatureConfig, FeatureInput, FeatureSnapshot, build_feature_snapshot_v2
from research.pumpfun_signals import SignalConfig, TradeSignal, generate_signal


@dataclass(frozen=True)
class ReplayStep:
    timestamp: int
    mint: str
    feature_snapshot: FeatureSnapshot
    signal: TradeSignal


@dataclass(frozen=True)
class ReplayResult:
    steps: tuple[ReplayStep, ...]


def replay_events(
    events: Iterable[TokenEvent],
    *,
    feature_config: FeatureConfig = FeatureConfig(),
    signal_config: SignalConfig = SignalConfig(),
) -> ReplayResult:
    ordered = tuple(sorted(events, key=lambda e: (e.timestamp, e.slot, e.signature)))
    if not ordered:
        return ReplayResult(())
    steps: list[ReplayStep] = []
    for index, current in enumerate(ordered):
        visible = tuple(e for e in ordered[: index + 1] if e.mint == current.mint)
        snap = build_feature_snapshot_v2(FeatureInput(visible), now=current.timestamp, config=feature_config)
        signal = generate_signal(snap, config=signal_config)
        steps.append(ReplayStep(current.timestamp, current.mint, snap, signal))
    return ReplayResult(tuple(steps))
