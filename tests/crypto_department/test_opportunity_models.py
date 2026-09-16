"""Tests for crypto opportunity models."""

import json
import pytest

from agent.crypto_department.opportunity_models import (
    AutomationPermitted,
    Opportunity,
    OpportunitySource,
    OpportunityStatus,
    OpportunityType,
    RiskLevel,
    ScoringDimensions,
    ScoringResult,
)


class TestOpportunityType:
    def test_all_types_have_values(self):
        for t in OpportunityType:
            assert isinstance(t.value, str)
            assert len(t.value) > 0

    def test_string_enum_behavior(self):
        assert OpportunityType.AIRDROP == "airdrop"
        assert OpportunityType.QUEST == "quest"
        assert OpportunityType("faucet") == OpportunityType.FAUCET


class TestOpportunityStatus:
    def test_all_statuses(self):
        statuses = list(OpportunityStatus)
        assert len(statuses) >= 10
        assert OpportunityStatus.DISCOVERED in statuses
        assert OpportunityStatus.COMPLETED in statuses
        assert OpportunityStatus.EXPIRED in statuses


class TestOpportunity:
    def test_create_with_defaults(self):
        opp = Opportunity()
        assert opp.id
        assert opp.type == OpportunityType.OTHER
        assert opp.status == OpportunityStatus.DISCOVERED
        assert opp.rank == 0
        assert opp.is_active()

    def test_to_dict_roundtrip(self):
        opp = Opportunity(
            type=OpportunityType.AIRDROP,
            name="Test Airdrop",
            description="Free tokens",
            chain="ethereum",
            status=OpportunityStatus.ELIGIBLE,
        )
        d = opp.to_dict()
        opp2 = Opportunity.from_dict(d)
        assert opp2.type == OpportunityType.AIRDROP
        assert opp2.name == "Test Airdrop"
        assert opp2.chain == "ethereum"
        assert opp2.status == OpportunityStatus.ELIGIBLE

    def test_to_json_roundtrip(self):
        opp = Opportunity(
            type=OpportunityType.QUEST,
            name="Quest Test",
            scoring=ScoringDimensions(expected_reward_usd=50.0, risk_score=0.3),
        )
        j = opp.to_json()
        opp2 = Opportunity.from_json(j)
        assert opp2.type == OpportunityType.QUEST
        assert opp2.scoring.expected_reward_usd == 50.0
        assert opp2.scoring.risk_score == 0.3

    def test_is_active_true_for_discovered(self):
        opp = Opportunity(status=OpportunityStatus.DISCOVERED)
        assert opp.is_active()

    def test_is_active_false_for_expired(self):
        opp = Opportunity(status=OpportunityStatus.EXPIRED)
        assert not opp.is_active()

    def test_is_active_false_for_completed(self):
        opp = Opportunity(status=OpportunityStatus.COMPLETED)
        assert not opp.is_active()

    def test_is_active_false_for_ineligible(self):
        opp = Opportunity(status=OpportunityStatus.INELIGIBLE)
        assert not opp.is_active()

    def test_is_deadline_approaching_no_deadline(self):
        opp = Opportunity()
        assert not opp.is_deadline_approaching()

    def test_with_source(self):
        source = OpportunitySource(
            name="test_source",
            url="https://example.com",
            reliability=0.8,
            evidence=["verified by team"],
        )
        opp = Opportunity(source=source)
        d = opp.to_dict()
        opp2 = Opportunity.from_dict(d)
        assert opp2.source.name == "test_source"
        assert opp2.source.reliability == 0.8
        assert opp2.source.evidence == ["verified by team"]

    def test_with_result(self):
        result = ScoringResult(
            expected_value_usd=100.0,
            total_cost_usd=20.0,
            net_value_usd=80.0,
            composite_score=8.5,
            recommendation="HIGH_PRIORITY",
        )
        opp = Opportunity(result=result)
        d = opp.to_dict()
        opp2 = Opportunity.from_dict(d)
        assert opp2.result is not None
        assert opp2.result.net_value_usd == 80.0
        assert opp2.result.recommendation == "HIGH_PRIORITY"


class TestScoringDimensions:
    def test_defaults(self):
        sd = ScoringDimensions()
        assert sd.expected_reward_usd == 0.0
        assert sd.fees_usd == 0.0
        assert sd.time_cost_hours == 0.0
        assert sd.risk_score == 0.0
        assert sd.confidence == 0.5
        assert sd.automation_permit == AutomationPermitted.NONE

    def test_roundtrip(self):
        sd = ScoringDimensions(
            expected_reward_usd=100.0,
            fees_usd=5.0,
            time_cost_hours=2.0,
            risk_score=0.4,
            confidence=0.8,
            automation_permit=AutomationPermitted.PARTIAL,
            risk_level=RiskLevel.MEDIUM,
        )
        d = sd.to_dict()
        sd2 = ScoringDimensions.from_dict(d)
        assert sd2.expected_reward_usd == 100.0
        assert sd2.automation_permit == AutomationPermitted.PARTIAL
        assert sd2.risk_level == RiskLevel.MEDIUM
