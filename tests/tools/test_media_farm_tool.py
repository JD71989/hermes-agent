"""Tests for the Guardian Media Farm tool handler (tools/media_farm_tool)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def media_farm_home(tmp_path, monkeypatch):
    """Isolated HERMES_HOME with an empty media farm DB."""
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    from tools import media_farm_db as db_mod
    db_mod.init_db()
    return home


def _call(action: str, **kwargs) -> dict:
    from tools.media_farm_tool import _handle_media_farm
    args = {"action": action, **kwargs}
    result = _handle_media_farm(args)
    return json.loads(result)


# ---------------------------------------------------------------------------
# Campaign tool actions
# ---------------------------------------------------------------------------


def test_tool_create_campaign():
    r = _call("create_campaign", name="Test", campaign_type="social")
    assert r["success"] is True
    assert r["campaign"]["name"] == "Test"
    assert r["campaign"]["id"] > 0


def test_tool_list_campaigns():
    _call("create_campaign", name="A")
    _call("create_campaign", name="B")
    r = _call("list_campaigns")
    assert r["success"] is True
    assert r["count"] == 2


def test_tool_get_campaign():
    c = _call("create_campaign", name="Get Me")
    r = _call("get_campaign", campaign_id=c["campaign"]["id"])
    assert r["success"] is True
    assert r["campaign"]["name"] == "Get Me"


def test_tool_get_nonexistent_campaign():
    r = _call("get_campaign", campaign_id=99999)
    assert "error" in r


def test_tool_update_campaign():
    c = _call("create_campaign", name="Original")
    r = _call("update_campaign", campaign_id=c["campaign"]["id"], name="Updated", status="active")
    assert r["success"] is True
    assert r["campaign"]["name"] == "Updated"


def test_tool_campaign_summary():
    c = _call("create_campaign", name="Summary")
    r = _call("campaign_summary", campaign_id=c["campaign"]["id"])
    assert r["success"] is True
    assert "summary" in r


# ---------------------------------------------------------------------------
# Content tool actions
# ---------------------------------------------------------------------------


def test_tool_create_content():
    r = _call("create_content", title="Post", content_type="post", platform="x")
    assert r["success"] is True
    assert r["content"]["title"] == "Post"
    assert r["content"]["platform"] == "x"


def test_tool_list_content():
    _call("create_content", title="A", platform="x")
    _call("create_content", title="B", platform="instagram")
    r = _call("list_content", platform="x")
    assert r["success"] is True
    assert r["count"] == 1


def test_tool_update_content():
    c = _call("create_content", title="Original")
    r = _call("update_content", content_id=c["content"]["id"], hook="New hook", status="hook")
    assert r["success"] is True
    assert r["content"]["hook"] == "New hook"


def test_tool_delete_content():
    c = _call("create_content", title="Delete Me")
    r = _call("delete_content", content_id=c["content"]["id"])
    assert r["success"] is True
    assert r["deleted"] is True


def test_tool_content_performance():
    c = _call("create_content", title="Perf")
    _call("record_engagement", content_id=c["content"]["id"], platform="x", likes=100)
    r = _call("content_performance", content_id=c["content"]["id"])
    assert r["success"] is True
    assert r["performance"]["likes"] == 100


# ---------------------------------------------------------------------------
# Influencer tool actions
# ---------------------------------------------------------------------------


def test_tool_create_influencer():
    r = _call("create_influencer", handle="@creator", platform="x", followers=50000)
    assert r["success"] is True
    assert r["influencer"]["handle"] == "@creator"


def test_tool_list_influencers():
    _call("create_influencer", handle="@a", niche="tech")
    _call("create_influencer", handle="@b", niche="fashion")
    r = _call("list_influencers", niche="tech")
    assert r["count"] == 1


def test_tool_influencer_roi():
    inf = _call("create_influencer", handle="@roi")
    c = _call("create_campaign", name="ROI Camp")
    _call("create_influencer_campaign",
          influencer_id=inf["influencer"]["id"],
          campaign_id=c["campaign"]["id"],
          cost=500.0)
    _call("record_conversion",
          influencer_id=inf["influencer"]["id"],
          campaign_id=c["campaign"]["id"],
          revenue=2000.0)
    r = _call("influencer_roi", influencer_id=inf["influencer"]["id"])
    assert r["success"] is True
    assert r["roi"]["roi_percent"] == 300.0


# ---------------------------------------------------------------------------
# Asset tool actions
# ---------------------------------------------------------------------------


def test_tool_create_asset():
    r = _call("create_asset", name="Image", asset_type="image", width=1080, height=1080)
    assert r["success"] is True
    assert r["asset"]["width"] == 1080


def test_tool_list_assets():
    _call("create_asset", name="A", asset_type="image")
    _call("create_asset", name="B", asset_type="video")
    r = _call("list_assets", asset_type="image")
    assert r["count"] == 1


# ---------------------------------------------------------------------------
# Engagement tool actions
# ---------------------------------------------------------------------------


def test_tool_record_engagement():
    c = _call("create_content", title="Engage")
    r = _call("record_engagement", content_id=c["content"]["id"], platform="x",
              impressions=5000, likes=200)
    assert r["success"] is True
    assert r["engagement"]["impressions"] == 5000


def test_tool_get_engagements():
    c = _call("create_content", title="Multi")
    _call("record_engagement", content_id=c["content"]["id"], platform="x")
    _call("record_engagement", content_id=c["content"]["id"], platform="instagram")
    r = _call("get_engagements", content_id=c["content"]["id"])
    assert r["count"] == 2


# ---------------------------------------------------------------------------
# Conversion tool actions
# ---------------------------------------------------------------------------


def test_tool_record_conversion():
    r = _call("record_conversion", conversion_type="lead", revenue=100.0)
    assert r["success"] is True
    assert r["conversion"]["revenue"] == 100.0


def test_tool_get_conversions():
    _call("record_conversion", conversion_type="lead")
    _call("record_conversion", conversion_type="sale")
    r = _call("get_conversions")
    assert r["count"] == 2


# ---------------------------------------------------------------------------
# Schedule tool actions
# ---------------------------------------------------------------------------


def test_tool_create_schedule():
    c = _call("create_content", title="Scheduled")
    r = _call("create_schedule", content_id=c["content"]["id"], platform="x", scheduled_at=1000000)
    assert r["success"] is True


def test_tool_get_schedules():
    c = _call("create_content", title="Schedules")
    _call("create_schedule", content_id=c["content"]["id"], platform="x", scheduled_at=1000000)
    r = _call("get_schedules", content_id=c["content"]["id"])
    assert r["count"] == 1


# ---------------------------------------------------------------------------
# Video tool actions
# ---------------------------------------------------------------------------


def test_tool_create_video():
    r = _call("create_video", title="Demo Video", brief="Show the product")
    assert r["success"] is True
    assert r["video"]["title"] == "Demo Video"


def test_tool_list_videos():
    _call("create_video", title="A")
    _call("create_video", title="B")
    r = _call("list_videos")
    assert r["count"] == 2


def test_tool_update_video():
    v = _call("create_video", title="Original")
    r = _call("update_video", video_id=v["video"]["id"], status="script", script="Scene 1")
    assert r["success"] is True
    assert r["video"]["status"] == "script"


# ---------------------------------------------------------------------------
# Attribution tool actions
# ---------------------------------------------------------------------------


def test_tool_record_attribution():
    r = _call("record_attribution", channel="x", revenue=5000.0, cost=1000.0)
    assert r["success"] is True
    assert r["attribution"]["roi"] == 400.0


def test_tool_get_attribution():
    _call("record_attribution", channel="x")
    _call("record_attribution", channel="instagram")
    r = _call("get_attribution")
    assert r["count"] == 2


# ---------------------------------------------------------------------------
# Analytics tool actions
# ---------------------------------------------------------------------------


def test_tool_top_content():
    c = _call("create_content", title="Popular")
    _call("record_engagement", content_id=c["content"]["id"], platform="x", likes=100)
    r = _call("top_content", limit=5)
    assert r["success"] is True
    assert len(r["top_content"]) >= 1


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_tool_unknown_action():
    r = _call("nonexistent_action")
    assert "error" in r


def test_tool_missing_required_fields():
    r = _call("create_campaign")
    assert r["success"] is True  # name has default
