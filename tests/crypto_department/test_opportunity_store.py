"""Tests for the crypto opportunity store."""

import json
import pytest
from pathlib import Path

from agent.crypto_department.opportunity_models import (
    Opportunity,
    OpportunityStatus,
    OpportunityType,
    ScoringDimensions,
)
from agent.crypto_department.opportunity_store import OpportunityStore


@pytest.fixture
def store(tmp_path):
    """Create a temporary opportunity store."""
    return OpportunityStore(base_dir=tmp_path / "crypto_intel")


class TestOpportunityStore:
    def test_upsert_and_get(self, store):
        opp = Opportunity(
            name="Test Airdrop",
            type=OpportunityType.AIRDROP,
            chain="ethereum",
        )
        store.upsert(opp)
        retrieved = store.get(opp.id)
        assert retrieved is not None
        assert retrieved.name == "Test Airdrop"
        assert retrieved.type == OpportunityType.AIRDROP

    def test_upsert_updates_existing(self, store):
        opp = Opportunity(name="Original Name")
        store.upsert(opp)
        opp.name = "Updated Name"
        store.upsert(opp)
        retrieved = store.get(opp.id)
        assert retrieved.name == "Updated Name"

    def test_get_nonexistent(self, store):
        assert store.get("nonexistent-id") is None

    def test_list_all(self, store):
        for i in range(5):
            store.upsert(Opportunity(name=f"Opp {i}"))
        all_opps = store.list_all()
        assert len(all_opps) == 5

    def test_list_filter_by_status(self, store):
        store.upsert(Opportunity(name="Discovered", status=OpportunityStatus.DISCOVERED))
        store.upsert(Opportunity(name="Completed", status=OpportunityStatus.COMPLETED))
        discovered = store.list_all(status=OpportunityStatus.DISCOVERED)
        assert len(discovered) == 1
        assert discovered[0].name == "Discovered"

    def test_list_filter_by_type(self, store):
        store.upsert(Opportunity(name="Airdrop", type=OpportunityType.AIRDROP))
        store.upsert(Opportunity(name="Quest", type=OpportunityType.QUEST))
        airdrops = store.list_all(opp_type=OpportunityType.AIRDROP)
        assert len(airdrops) == 1
        assert airdrops[0].name == "Airdrop"

    def test_list_filter_by_project(self, store):
        store.upsert(Opportunity(name="Opp1", project="ProtocolA"))
        store.upsert(Opportunity(name="Opp2", project="ProtocolB"))
        pa = store.list_all(project="ProtocolA")
        assert len(pa) == 1

    def test_update_status(self, store):
        opp = Opportunity(name="Test", status=OpportunityStatus.DISCOVERED)
        store.upsert(opp)
        ok = store.update_status(opp.id, OpportunityStatus.IN_PROGRESS, "Starting work")
        assert ok
        updated = store.get(opp.id)
        assert updated.status == OpportunityStatus.IN_PROGRESS

    def test_update_status_records_history(self, store):
        opp = Opportunity(name="Test")
        store.upsert(opp)
        store.update_status(opp.id, OpportunityStatus.ELIGIBLE, "Checked eligibility")
        store.update_status(opp.id, OpportunityStatus.IN_PROGRESS, "Starting")
        history = store.get_history(opp.id)
        assert len(history) == 2
        assert history[0]["new_status"] == "eligible"
        assert history[1]["new_status"] == "in_progress"

    def test_update_status_nonexistent(self, store):
        ok = store.update_status("bad-id", OpportunityStatus.COMPLETED)
        assert not ok

    def test_delete(self, store):
        opp = Opportunity(name="ToDelete")
        store.upsert(opp)
        assert store.get(opp.id) is not None
        ok = store.delete(opp.id)
        assert ok
        assert store.get(opp.id) is None

    def test_count(self, store):
        assert store.count() == 0
        store.upsert(Opportunity(name="A"))
        store.upsert(Opportunity(name="B"))
        assert store.count() == 2

    def test_count_by_status(self, store):
        store.upsert(Opportunity(name="A", status=OpportunityStatus.DISCOVERED))
        store.upsert(Opportunity(name="B", status=OpportunityStatus.COMPLETED))
        assert store.count(status=OpportunityStatus.DISCOVERED) == 1
        assert store.count(status=OpportunityStatus.COMPLETED) == 1

    def test_summary(self, store):
        store.upsert(Opportunity(name="A", type=OpportunityType.AIRDROP))
        store.upsert(Opportunity(name="B", type=OpportunityType.QUEST))
        store.upsert(Opportunity(name="C", type=OpportunityType.AIRDROP))
        summary = store.summary()
        assert summary["total"] == 3
        assert summary["by_type"]["airdrop"] == 2
        assert summary["by_type"]["quest"] == 1

    def test_scoring_roundtrip(self, store):
        opp = Opportunity(
            name="Scored",
            scoring=ScoringDimensions(
                expected_reward_usd=100.0,
                risk_score=0.3,
                confidence=0.8,
            ),
        )
        store.upsert(opp)
        retrieved = store.get(opp.id)
        assert retrieved.scoring.expected_reward_usd == 100.0
        assert retrieved.scoring.risk_score == 0.3

    def test_list_ordering_by_rank(self, store):
        opp1 = Opportunity(name="First", rank=3)
        opp2 = Opportunity(name="Second", rank=1)
        opp3 = Opportunity(name="Third", rank=2)
        store.upsert(opp1)
        store.upsert(opp2)
        store.upsert(opp3)
        all_opps = store.list_all()
        assert all_opps[0].rank == 1
        assert all_opps[1].rank == 2
        assert all_opps[2].rank == 3

    def test_limit(self, store):
        for i in range(10):
            store.upsert(Opportunity(name=f"Opp {i}"))
        limited = store.list_all(limit=3)
        assert len(limited) == 3
