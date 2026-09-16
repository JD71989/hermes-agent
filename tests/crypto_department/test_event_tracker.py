"""Tests for the crypto event tracker."""

import pytest
from datetime import datetime, timezone, timedelta

from agent.crypto_department.event_tracker import EventTracker


@pytest.fixture
def tracker(tmp_path):
    """Create a temporary event tracker."""
    return EventTracker(base_dir=tmp_path / "crypto_intel")


class TestEventTracker:
    def test_add_and_get(self, tracker):
        event_id = tracker.add_event(
            title="Token Unlock",
            event_type="token_unlock",
            project="TestProtocol",
            chain="ethereum",
        )
        event = tracker.get_event(event_id)
        assert event is not None
        assert event["title"] == "Token Unlock"
        assert event["event_type"] == "token_unlock"

    def test_add_with_end_time(self, tracker):
        future = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
        event_id = tracker.add_event(
            title="Airdrop Deadline",
            event_type="airdrop_deadline",
            end_time=future,
        )
        event = tracker.get_event(event_id)
        assert event["end_time"] is not None

    def test_list_events(self, tracker):
        tracker.add_event(title="Event 1", event_type="token_unlock")
        tracker.add_event(title="Event 2", event_type="governance_vote")
        events = tracker.list_events()
        assert len(events) == 2

    def test_list_filter_by_type(self, tracker):
        tracker.add_event(title="Unlock", event_type="token_unlock")
        tracker.add_event(title="Vote", event_type="governance_vote")
        unlocks = tracker.list_events(event_type="token_unlock")
        assert len(unlocks) == 1
        assert unlocks[0]["title"] == "Unlock"

    def test_list_filter_by_project(self, tracker):
        tracker.add_event(title="E1", project="ProtocolA")
        tracker.add_event(title="E2", project="ProtocolB")
        pa = tracker.list_events(project="ProtocolA")
        assert len(pa) == 1

    def test_get_expiring(self, tracker):
        soon = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
        later = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()
        tracker.add_event(title="Soon", end_time=soon)
        tracker.add_event(title="Later", end_time=later)
        expiring = tracker.get_expiring(hours=24)
        assert len(expiring) == 1
        assert expiring[0]["title"] == "Soon"

    def test_get_expiring_notifies_once(self, tracker):
        soon = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
        event_id = tracker.add_event(title="Soon", end_time=soon)
        expiring = tracker.get_expiring(hours=24)
        assert len(expiring) == 1
        tracker.mark_notified(event_id)
        expiring2 = tracker.get_expiring(hours=24)
        assert len(expiring2) == 0

    def test_delete_event(self, tracker):
        event_id = tracker.add_event(title="ToDelete")
        assert tracker.get_event(event_id) is not None
        ok = tracker.delete_event(event_id)
        assert ok
        assert tracker.get_event(event_id) is None

    def test_delete_nonexistent(self, tracker):
        ok = tracker.delete_event("nonexistent")
        assert not ok

    def test_count(self, tracker):
        assert tracker.count() == 0
        tracker.add_event(title="E1")
        tracker.add_event(title="E2")
        assert tracker.count() == 2

    def test_summary(self, tracker):
        tracker.add_event(title="E1", event_type="token_unlock")
        tracker.add_event(title="E2", event_type="airdrop_deadline")
        tracker.add_event(title="E3", event_type="token_unlock")
        summary = tracker.summary()
        assert summary["total"] == 3
        assert summary["by_type"]["token_unlock"] == 2
        assert summary["by_type"]["airdrop_deadline"] == 1

    def test_importance_levels(self, tracker):
        event_id = tracker.add_event(
            title="Critical Event",
            importance="critical",
        )
        event = tracker.get_event(event_id)
        assert event["importance"] == "critical"

    def test_source_url(self, tracker):
        event_id = tracker.add_event(
            title="Event with URL",
            source_url="https://example.com/announcement",
        )
        event = tracker.get_event(event_id)
        assert event["source_url"] == "https://example.com/announcement"
