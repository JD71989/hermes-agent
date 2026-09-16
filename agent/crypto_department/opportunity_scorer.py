"""Opportunity scorer for the Crypto Intelligence Department.

Implements the scoring formula:
  EXPECTED VALUE
  minus FEES
  minus TIME COST
  minus RISK

Produces composite scores and rankings.
"""

from __future__ import annotations

import math
from typing import List, Optional

from agent.crypto_department.opportunity_models import (
    AutomationPermitted,
    Opportunity,
    RiskLevel,
    ScoringDimensions,
    ScoringResult,
)


def _risk_multiplier(risk_score: float, confidence: float) -> float:
    """Convert risk_score (0-1, higher = riskier) to a multiplier (0-1).

    High risk + low confidence => low multiplier.
    Low risk + high confidence => high multiplier.
    """
    risk_factor = 1.0 - risk_score
    conf_factor = confidence
    return (risk_factor * 0.6) + (conf_factor * 0.4)


def _risk_level_from_score(risk_score: float) -> RiskLevel:
    if risk_score <= 0.15:
        return RiskLevel.VERY_LOW
    if risk_score <= 0.35:
        return RiskLevel.LOW
    if risk_score <= 0.60:
        return RiskLevel.MEDIUM
    if risk_score <= 0.85:
        return RiskLevel.HIGH
    return RiskLevel.VERY_HIGH


def _hourly_value(time_cost_hours: float, net_value: float) -> float:
    if time_cost_hours <= 0:
        return net_value * 10.0
    return net_value / time_cost_hours


def _automation_discount(permit: AutomationPermitted, time_hours: float) -> float:
    """Estimate time savings from automation (where permitted)."""
    if permit == AutomationPermitted.FULL:
        return time_hours * 0.9
    if permit == AutomationPermitted.PARTIAL:
        return time_hours * 0.5
    if permit == AutomationPermitted.READ_ONLY:
        return time_hours * 0.1
    return 0.0


def _hourly_wage_usd() -> float:
    """Baseline hourly cost estimate (gas/time/opportunity cost)."""
    return 25.0


def score_opportunity(
    dims: ScoringDimensions,
    hourly_wage: Optional[float] = None,
) -> ScoringResult:
    """Score an opportunity using: EV - fees - time cost - risk.

    Args:
        dims: Scoring dimensions (reward, fees, time, risk, confidence).
        hourly_wage: Override hourly cost rate (default: $25/h).

    Returns:
        ScoringResult with full breakdown and composite score.
    """
    wage = hourly_wage if hourly_wage is not None else _hourly_wage_usd()

    ev = dims.expected_reward_usd
    fees = dims.fees_usd
    upfront = dims.upfront_cost_usd
    gas = dims.gas_cost_usd

    auto_saved_hours = _automation_discount(dims.automation_permit, dims.time_cost_hours)
    effective_hours = max(0.0, dims.time_cost_hours - auto_saved_hours)
    time_cost_usd = effective_hours * wage

    total_cost = fees + time_cost_usd + upfront + gas
    net_value = max(0.0, ev - total_cost)
    ev_per_hour = _hourly_value(effective_hours, net_value)

    risk_mult = _risk_multiplier(dims.risk_score, dims.confidence)
    risk_adjusted = net_value * risk_mult

    cost_breakdown = {
        "fees_usd": round(fees, 4),
        "time_cost_usd": round(time_cost_usd, 4),
        "upfront_cost_usd": round(upfront, 4),
        "gas_cost_usd": round(gas, 4),
        "automation_saved_hours": round(auto_saved_hours, 2),
        "effective_hours": round(effective_hours, 2),
    }

    if risk_adjusted <= 0:
        recommendation = "SKIP"
    elif risk_adjusted < 1.0:
        recommendation = "LOW_PRIORITY"
    elif ev_per_hour < wage * 0.5:
        recommendation = "LOW_PRIORITY"
    elif risk_adjusted >= 10.0 and dims.confidence >= 0.7:
        recommendation = "HIGH_PRIORITY"
    else:
        recommendation = "PRIORITY"

    composite = (risk_adjusted * 0.5) + (min(ev_per_hour / wage, 10.0) * 0.3) + (dims.confidence * 0.2 * 10.0)

    return ScoringResult(
        expected_value_usd=round(ev, 4),
        total_cost_usd=round(total_cost, 4),
        net_value_usd=round(net_value, 4),
        expected_value_per_hour=round(ev_per_hour, 4),
        risk_adjusted_value=round(risk_adjusted, 4),
        composite_score=round(composite, 4),
        recommendation=recommendation,
        cost_breakdown=cost_breakdown,
    )


def rank_opportunities(
    opportunities: List[Opportunity],
    hourly_wage: Optional[float] = None,
) -> List[Opportunity]:
    """Score all opportunities and return sorted by composite_score descending.

    Only active opportunities are ranked. Inactive ones keep rank=0.
    """
    active = [o for o in opportunities if o.is_active()]
    inactive = [o for o in opportunities if not o.is_active()]

    for opp in active:
        opp.result = score_opportunity(opp.scoring, hourly_wage=hourly_wage)
        opp.scoring.risk_level = _risk_level_from_score(opp.scoring.risk_score)

    active.sort(key=lambda o: o.result.composite_score if o.result else 0, reverse=True)

    for i, opp in enumerate(active, 1):
        opp.rank = i

    return active + inactive
