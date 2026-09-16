"""Tests for crypto intelligence tools — handler-level tests."""

import json
import pytest
from pathlib import Path

from tools.crypto_opportunity_discover import _handle_crypto_opportunity_discover
from tools.crypto_opportunity_score import _handle_crypto_opportunity_score
from tools.crypto_opportunity_track import _handle_crypto_opportunity_track
from tools.crypto_event_track import _handle_crypto_event_track


class TestCryptoOpportunityDiscover:
    def test_discover_all(self):
        result = _handle_crypto_opportunity_discover({})
        data = json.loads(result)
        assert "discovered" in data
        assert "opportunities" in data
        assert data["discovered"] > 0
        assert isinstance(data["opportunities"], list)

    def test_discover_filter_by_type(self):
        result = _handle_crypto_opportunity_discover({
            "opportunity_types": ["airdrop"],
        })
        data = json.loads(result)
        assert data["discovered"] >= 1
        for opp in data["opportunities"]:
            assert opp["type"] == "airdrop"

    def test_discover_filter_by_chain(self):
        result = _handle_crypto_opportunity_discover({
            "chains": ["ethereum"],
        })
        data = json.loads(result)
        for opp in data["opportunities"]:
            assert opp["chain"] in ("ethereum", "multi")

    def test_discover_has_required_actions(self):
        result = _handle_crypto_opportunity_discover({})
        data = json.loads(result)
        for opp in data["opportunities"]:
            assert "required_actions" in opp
            assert isinstance(opp["required_actions"], list)

    def test_discover_has_scoring(self):
        result = _handle_crypto_opportunity_discover({})
        data = json.loads(result)
        for opp in data["opportunities"]:
            assert "scoring" in opp
            assert "risk_score" in opp["scoring"]
            assert "confidence" in opp["scoring"]

    def test_discover_limit(self):
        result = _handle_crypto_opportunity_discover({"limit": 2})
        data = json.loads(result)
        assert data["discovered"] <= 2

    def test_discover_max_risk_filter(self):
        result = _handle_crypto_opportunity_discover({"max_risk_score": 0.2})
        data = json.loads(result)
        for opp in data["opportunities"]:
            assert opp["scoring"]["risk_score"] <= 0.2

    def test_discover_stores_in_db(self):
        result = _handle_crypto_opportunity_discover({"limit": 3})
        data = json.loads(result)
        assert data["summary"]["total"] >= 1


class TestCryptoOpportunityScore:
    def test_score_new_opportunity(self):
        result = _handle_crypto_opportunity_score({
            "expected_reward_usd": 100.0,
            "fees_usd": 5.0,
            "time_cost_hours": 2.0,
            "risk_score": 0.2,
            "confidence": 0.8,
        })
        data = json.loads(result)
        assert "result" in data
        assert data["result"]["expected_value_usd"] == 100.0
        assert data["result"]["net_value_usd"] > 0

    def test_score_with_automation(self):
        result = _handle_crypto_opportunity_score({
            "expected_reward_usd": 50.0,
            "time_cost_hours": 5.0,
            "risk_score": 0.2,
            "confidence": 0.8,
            "automation_permit": "full",
        })
        data = json.loads(result)
        assert data["result"]["cost_breakdown"]["automation_saved_hours"] > 0

    def test_score_existing_opportunity(self):
        discover_result = _handle_crypto_opportunity_discover({"limit": 1})
        discover_data = json.loads(discover_result)
        opp_id = discover_data["opportunities"][0]["id"]

        score_result = _handle_crypto_opportunity_score({
            "opportunity_id": opp_id,
            "expected_reward_usd": 200.0,
            "risk_score": 0.1,
        })
        score_data = json.loads(score_result)
        assert score_data["scoring"]["expected_reward_usd"] == 200.0

    def test_score_nonexistent_opp(self):
        result = _handle_crypto_opportunity_score({
            "opportunity_id": "nonexistent",
            "expected_reward_usd": 100.0,
        })
        assert "error" in json.loads(result)

    def test_score_with_evidence(self):
        result = _handle_crypto_opportunity_score({
            "expected_reward_usd": 50.0,
            "evidence": ["Confirmed by team", "Verified contract"],
        })
        data = json.loads(result)
        assert "result" in data

    def test_score_with_deadline(self):
        result = _handle_crypto_opportunity_score({
            "expected_reward_usd": 50.0,
            "deadline": "2026-12-31T23:59:59Z",
        })
        data = json.loads(result)
        assert "result" in data


class TestCryptoOpportunityTrack:
    def test_summary_empty(self):
        result = _handle_crypto_opportunity_track({"action": "summary"})
        data = json.loads(result)
        assert "total" in data
        assert data["total"] == 0

    def test_summary_after_discover(self):
        _handle_crypto_opportunity_discover({"limit": 3})
        result = _handle_crypto_opportunity_track({"action": "summary"})
        data = json.loads(result)
        assert data["total"] >= 1

    def test_list_opportunities(self):
        _handle_crypto_opportunity_discover({"limit": 2})
        result = _handle_crypto_opportunity_track({"action": "list"})
        data = json.loads(result)
        assert data["count"] >= 1

    def test_update_status(self):
        discover_result = _handle_crypto_opportunity_discover({"limit": 1})
        opp_id = json.loads(discover_result)["opportunities"][0]["id"]

        update_result = _handle_crypto_opportunity_track({
            "action": "update_status",
            "opportunity_id": opp_id,
            "new_status": "in_progress",
            "notes": "Starting work",
        })
        data = json.loads(update_result)
        assert data["updated"] is True
        assert data["opportunity"]["status"] == "in_progress"

    def test_status_nonexistent(self):
        result = _handle_crypto_opportunity_track({
            "action": "update_status",
            "opportunity_id": "bad-id",
            "new_status": "completed",
        })
        assert "error" in json.loads(result)

    def test_get_status(self):
        discover_result = _handle_crypto_opportunity_discover({"limit": 1})
        opp_id = json.loads(discover_result)["opportunities"][0]["id"]
        result = _handle_crypto_opportunity_track({
            "action": "status",
            "opportunity_id": opp_id,
        })
        data = json.loads(result)
        assert data["id"] == opp_id

    def test_history(self):
        discover_result = _handle_crypto_opportunity_discover({"limit": 1})
        opp_id = json.loads(discover_result)["opportunities"][0]["id"]
        _handle_crypto_opportunity_track({
            "action": "update_status",
            "opportunity_id": opp_id,
            "new_status": "in_progress",
        })
        result = _handle_crypto_opportunity_track({
            "action": "history",
            "opportunity_id": opp_id,
        })
        data = json.loads(result)
        assert len(data["history"]) == 1

    def test_delete(self):
        discover_result = _handle_crypto_opportunity_discover({"limit": 1})
        opp_id = json.loads(discover_result)["opportunities"][0]["id"]
        result = _handle_crypto_opportunity_track({
            "action": "delete",
            "opportunity_id": opp_id,
        })
        data = json.loads(result)
        assert data["deleted"] is True

    def test_missing_action(self):
        result = _handle_crypto_opportunity_track({})
        assert "error" in json.loads(result)


class TestCryptoEventTrack:
    def test_add_event(self):
        result = _handle_crypto_event_track({
            "action": "add",
            "title": "Token Unlock",
            "event_type": "token_unlock",
            "project": "TestProtocol",
        })
        data = json.loads(result)
        assert data["added"] is True
        assert data["event"]["title"] == "Token Unlock"

    def test_add_event_missing_title(self):
        result = _handle_crypto_event_track({"action": "add"})
        assert "error" in json.loads(result)

    def test_list_events(self):
        _handle_crypto_event_track({
            "action": "add",
            "title": "Event 1",
        })
        _handle_crypto_event_track({
            "action": "add",
            "title": "Event 2",
        })
        result = _handle_crypto_event_track({"action": "list"})
        data = json.loads(result)
        assert data["count"] >= 2

    def test_list_filter_by_type(self):
        _handle_crypto_event_track({
            "action": "add",
            "title": "Unlock",
            "event_type": "token_unlock",
        })
        _handle_crypto_event_track({
            "action": "add",
            "title": "Vote",
            "event_type": "governance_vote",
        })
        result = _handle_crypto_event_track({
            "action": "list",
            "event_type": "token_unlock",
        })
        data = json.loads(result)
        assert data["count"] == 1

    def test_summary(self):
        _handle_crypto_event_track({
            "action": "add",
            "title": "Test Event",
        })
        result = _handle_crypto_event_track({"action": "summary"})
        data = json.loads(result)
        assert data["total"] >= 1

    def test_delete_event(self):
        add_result = _handle_crypto_event_track({
            "action": "add",
            "title": "To Delete",
        })
        event_id = json.loads(add_result)["event"]["id"]
        result = _handle_crypto_event_track({
            "action": "delete",
            "event_id": event_id,
        })
        data = json.loads(result)
        assert data["deleted"] is True

    def test_expiring(self):
        from datetime import datetime, timezone, timedelta
        soon = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
        _handle_crypto_event_track({
            "action": "add",
            "title": "Expiring Soon",
            "end_time": soon,
        })
        result = _handle_crypto_event_track({
            "action": "expiring",
            "deadline_hours": 24,
        })
        data = json.loads(result)
        assert data["count"] >= 1

    def test_unknown_action(self):
        result = _handle_crypto_event_track({"action": "unknown"})
        assert "error" in json.loads(result)
