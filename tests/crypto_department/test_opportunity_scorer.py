"""Tests for the crypto opportunity scorer."""

import json
import pytest

from agent.crypto_department.opportunity_models import (
    AutomationPermitted,
    Opportunity,
    OpportunityType,
    RiskLevel,
    ScoringDimensions,
)
from agent.crypto_department.opportunity_scorer import (
    _risk_level_from_score,
    _risk_multiplier,
    rank_opportunities,
    score_opportunity,
)


class TestRiskMultiplier:
    def test_low_risk_high_confidence(self):
        mult = _risk_multiplier(risk_score=0.1, confidence=0.9)
        assert mult > 0.8

    def test_high_risk_low_confidence(self):
        mult = _risk_multiplier(risk_score=0.9, confidence=0.1)
        assert mult < 0.3

    def test_medium_risk_medium_confidence(self):
        mult = _risk_multiplier(risk_score=0.5, confidence=0.5)
        assert 0.4 < mult < 0.6

    def test_range(self):
        mult = _risk_multiplier(risk_score=0.0, confidence=1.0)
        assert mult == pytest.approx(1.0, abs=0.01)


class TestRiskLevel:
    def test_very_low(self):
        assert _risk_level_from_score(0.1) == RiskLevel.VERY_LOW

    def test_low(self):
        assert _risk_level_from_score(0.25) == RiskLevel.LOW

    def test_medium(self):
        assert _risk_level_from_score(0.5) == RiskLevel.MEDIUM

    def test_high(self):
        assert _risk_level_from_score(0.7) == RiskLevel.HIGH

    def test_very_high(self):
        assert _risk_level_from_score(0.9) == RiskLevel.VERY_HIGH


class TestScoreOpportunity:
    def test_high_value_low_cost(self):
        dims = ScoringDimensions(
            expected_reward_usd=100.0,
            fees_usd=5.0,
            time_cost_hours=1.0,
            risk_score=0.2,
            confidence=0.8,
        )
        result = score_opportunity(dims)
        assert result.expected_value_usd == 100.0
        assert result.total_cost_usd > 0
        assert result.net_value_usd > 0
        assert result.risk_adjusted_value > 0
        assert result.recommendation in ("PRIORITY", "HIGH_PRIORITY")

    def test_negative_value(self):
        dims = ScoringDimensions(
            expected_reward_usd=5.0,
            fees_usd=10.0,
            time_cost_hours=4.0,
            risk_score=0.8,
            confidence=0.3,
        )
        result = score_opportunity(dims)
        assert result.net_value_usd == 0.0
        assert result.recommendation == "SKIP"

    def test_zero_reward(self):
        dims = ScoringDimensions(
            expected_reward_usd=0.0,
            fees_usd=0.0,
            time_cost_hours=1.0,
            risk_score=0.5,
            confidence=0.5,
        )
        result = score_opportunity(dims)
        assert result.net_value_usd == 0.0
        assert result.recommendation == "SKIP"

    def test_automation_reduces_time_cost(self):
        dims_manual = ScoringDimensions(
            expected_reward_usd=50.0,
            fees_usd=0.0,
            time_cost_hours=10.0,
            risk_score=0.2,
            confidence=0.8,
            automation_permit=AutomationPermitted.NONE,
        )
        dims_auto = ScoringDimensions(
            expected_reward_usd=50.0,
            fees_usd=0.0,
            time_cost_hours=10.0,
            risk_score=0.2,
            confidence=0.8,
            automation_permit=AutomationPermitted.FULL,
        )
        result_manual = score_opportunity(dims_manual)
        result_auto = score_opportunity(dims_auto)
        assert result_auto.risk_adjusted_value > result_manual.risk_adjusted_value

    def test_gas_cost_included(self):
        dims = ScoringDimensions(
            expected_reward_usd=50.0,
            fees_usd=0.0,
            time_cost_hours=1.0,
            gas_cost_usd=10.0,
            risk_score=0.2,
            confidence=0.8,
        )
        result = score_opportunity(dims)
        assert result.cost_breakdown["gas_cost_usd"] == 10.0

    def test_upfront_cost_included(self):
        dims = ScoringDimensions(
            expected_reward_usd=100.0,
            fees_usd=0.0,
            time_cost_hours=1.0,
            upfront_cost_usd=50.0,
            risk_score=0.2,
            confidence=0.8,
        )
        result = score_opportunity(dims)
        assert result.cost_breakdown["upfront_cost_usd"] == 50.0

    def test_custom_hourly_wage(self):
        dims = ScoringDimensions(
            expected_reward_usd=50.0,
            fees_usd=0.0,
            time_cost_hours=2.0,
            risk_score=0.2,
            confidence=0.8,
        )
        result_low = score_opportunity(dims, hourly_wage=10.0)
        result_high = score_opportunity(dims, hourly_wage=50.0)
        assert result_low.net_value_usd > result_high.net_value_usd

    def test_cost_breakdown_completeness(self):
        dims = ScoringDimensions(expected_reward_usd=10.0)
        result = score_opportunity(dims)
        assert "fees_usd" in result.cost_breakdown
        assert "time_cost_usd" in result.cost_breakdown
        assert "upfront_cost_usd" in result.cost_breakdown
        assert "gas_cost_usd" in result.cost_breakdown
        assert "automation_saved_hours" in result.cost_breakdown
        assert "effective_hours" in result.cost_breakdown

    def test_composite_score_positive(self):
        dims = ScoringDimensions(
            expected_reward_usd=100.0,
            risk_score=0.1,
            confidence=0.9,
        )
        result = score_opportunity(dims)
        assert result.composite_score > 0

    def test_high_priority_classification(self):
        dims = ScoringDimensions(
            expected_reward_usd=500.0,
            fees_usd=0.0,
            time_cost_hours=0.5,
            risk_score=0.1,
            confidence=0.9,
        )
        result = score_opportunity(dims)
        assert result.recommendation == "HIGH_PRIORITY"

    def test_low_priority_classification(self):
        dims = ScoringDimensions(
            expected_reward_usd=60.0,
            fees_usd=2.0,
            time_cost_hours=2.0,
            risk_score=0.4,
            confidence=0.5,
        )
        result = score_opportunity(dims)
        assert result.recommendation == "LOW_PRIORITY"


class TestRankOpportunities:
    def test_ranking_order(self):
        opps = [
            Opportunity(
                name="Low Value",
                scoring=ScoringDimensions(
                    expected_reward_usd=10.0, risk_score=0.5, confidence=0.5,
                    time_cost_hours=4.0,
                ),
            ),
            Opportunity(
                name="High Value",
                scoring=ScoringDimensions(
                    expected_reward_usd=200.0, risk_score=0.1, confidence=0.9,
                    time_cost_hours=0.5,
                ),
            ),
            Opportunity(
                name="Medium Value",
                scoring=ScoringDimensions(
                    expected_reward_usd=50.0, risk_score=0.3, confidence=0.7,
                    time_cost_hours=2.0,
                ),
            ),
        ]
        ranked = rank_opportunities(opps)
        assert ranked[0].name == "High Value"
        assert ranked[0].rank == 1
        assert ranked[1].name == "Medium Value"
        assert ranked[1].rank == 2
        assert ranked[2].name == "Low Value"
        assert ranked[2].rank == 3

    def test_inactive_opps_get_zero_rank(self):
        from agent.crypto_department.opportunity_models import OpportunityStatus
        opps = [
            Opportunity(
                name="Active",
                scoring=ScoringDimensions(expected_reward_usd=100.0),
            ),
            Opportunity(
                name="Expired",
                status=OpportunityStatus.EXPIRED,
                scoring=ScoringDimensions(expected_reward_usd=500.0),
            ),
        ]
        ranked = rank_opportunities(opps)
        assert len(ranked) == 2
        expired = [o for o in ranked if o.name == "Expired"][0]
        assert expired.rank == 0

    def test_empty_list(self):
        ranked = rank_opportunities([])
        assert ranked == []

    def test_scoring_result_populated(self):
        opps = [
            Opportunity(
                name="Test",
                scoring=ScoringDimensions(
                    expected_reward_usd=100.0, risk_score=0.2, confidence=0.8,
                ),
            ),
        ]
        ranked = rank_opportunities(opps)
        assert ranked[0].result is not None
        assert ranked[0].result.net_value_usd > 0
