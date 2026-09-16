"""Registry for turning observed strategy videos into testable hypotheses."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class HypothesisStatus(str, Enum):
    OBSERVED = "observed"
    FORMALIZED = "formalized"
    TESTED = "tested"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True)
class Hypothesis:
    hypothesis_id: str
    observation: str
    formal_condition: str
    entry_rule: str
    exit_rule: str
    risk_rule: str
    max_hold_seconds: int | None = None
    min_liquidity_sol: float | None = None
    max_slippage_bps: float | None = None
    status: HypothesisStatus = HypothesisStatus.OBSERVED
    result: dict[str, float] = field(default_factory=dict)


@dataclass
class HypothesisRegistry:
    items: dict[str, Hypothesis] = field(default_factory=dict)

    def add(self, hypothesis: Hypothesis) -> None:
        if hypothesis.hypothesis_id in self.items:
            raise ValueError(f"duplicate hypothesis id: {hypothesis.hypothesis_id}")
        self.items[hypothesis.hypothesis_id] = hypothesis

    def update_result(self, hypothesis_id: str, **metrics: float) -> None:
        current = self.items[hypothesis_id]
        self.items[hypothesis_id] = Hypothesis(
            **{**current.__dict__, "status": HypothesisStatus.TESTED, "result": dict(metrics)}
        )
