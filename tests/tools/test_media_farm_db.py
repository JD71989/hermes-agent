"""Tests for the Guardian Media Farm DB layer (tools/media_farm_db)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from tools import media_farm_db as db


@pytest.fixture(autouse=True)
def media_farm_home(tmp_path, monkeypatch):
    """Isolated HERMES_HOME with an empty media farm DB."""
    db.reset_connection()
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    db.init_db()
    return home


# ---------------------------------------------------------------------------
# Schema / Init
# ---------------------------------------------------------------------------


def test_init_db_creates_tables():
    conn = db._get_conn()
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    table_names = {t["name"] for t in tables}
    expected = {
        "content", "campaigns", "influencers", "influencer_campaigns",
        "assets", "engagements", "conversions", "schedules",
        "video_pipeline", "attribution", "state_meta",
    }
    assert expected.issubset(table_names)


def test_init_db_sets_schema_version():
    conn = db._get_conn()
    row = conn.execute(
        "SELECT value FROM state_meta WHERE key = 'schema_version'"
    ).fetchone()
    assert row is not None
    assert row["value"] == str(db.SCHEMA_VERSION)


def test_init_db_is_idempotent():
    db.init_db()
    db.init_db()
    conn = db._get_conn()
    count = conn.execute("SELECT COUNT(*) FROM campaigns").fetchone()[0]
    assert count == 0


# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------


def test_create_campaign():
    c = db.create_campaign("Test Campaign", campaign_type="social", budget=500.0)
    assert c["id"] > 0
    assert c["name"] == "Test Campaign"
    assert c["campaign_type"] == "social"
    assert c["budget"] == 500.0
    assert c["status"] == "draft"
    assert c["created_at"] > 0


def test_create_campaign_with_platforms():
    c = db.create_campaign("Multi-Platform", platforms=["x", "instagram", "tiktok"])
    assert c["platforms"] == ["x", "instagram", "tiktok"]


def test_get_campaign():
    c = db.create_campaign("Get Test")
    result = db.get_campaign(c["id"])
    assert result is not None
    assert result["name"] == "Get Test"


def test_get_nonexistent_campaign():
    result = db.get_campaign(99999)
    assert result is None


def test_list_campaigns():
    db.create_campaign("Campaign A")
    db.create_campaign("Campaign B")
    db.create_campaign("Campaign C")
    result = db.list_campaigns()
    assert len(result) == 3


def test_list_campaigns_by_status():
    db.create_campaign("Active", status="active")
    db.create_campaign("Draft", status="draft")
    result = db.list_campaigns(status="active")
    assert len(result) == 1
    assert result[0]["name"] == "Active"


def test_update_campaign():
    c = db.create_campaign("Original")
    updated = db.update_campaign(c["id"], name="Updated", status="active")
    assert updated["name"] == "Updated"
    assert updated["status"] == "active"


def test_campaign_summary():
    c = db.create_campaign("Summary Test")
    summary = db.get_campaign_summary(c["id"])
    assert summary["campaign_id"] == c["id"]
    assert summary["content_total"] == 0
    assert summary["impressions"] == 0
    assert summary["conversions"] == 0
    assert summary["roi_percent"] == 0.0


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------


def test_create_content():
    content = db.create_content("Test Post", content_type="post", platform="x")
    assert content["id"] > 0
    assert content["title"] == "Test Post"
    assert content["platform"] == "x"
    assert content["status"] == "idea"


def test_create_content_with_campaign():
    c = db.create_campaign("Campaign")
    content = db.create_content("Linked Post", campaign_id=c["id"])
    assert content["campaign_id"] == c["id"]


def test_get_content():
    content = db.create_content("Get Me")
    result = db.get_content(content["id"])
    assert result is not None
    assert result["title"] == "Get Me"


def test_list_content_filters():
    db.create_content("X Post", platform="x")
    db.create_content("IG Post", platform="instagram")
    db.create_content("X Post 2", platform="x")
    x_posts = db.list_content(platform="x")
    assert len(x_posts) == 2
    ig_posts = db.list_content(platform="instagram")
    assert len(ig_posts) == 1


def test_update_content():
    content = db.create_content("Original")
    updated = db.update_content(content["id"], hook="New hook", status="hook")
    assert updated["hook"] == "New hook"
    assert updated["status"] == "hook"


def test_update_content_json_fields():
    content = db.create_content("JSON Test")
    updated = db.update_content(content["id"], media_urls=["url1", "url2"], tags=["tag1"])
    assert updated["media_urls"] == ["url1", "url2"]
    assert updated["tags"] == ["tag1"]


def test_delete_content():
    content = db.create_content("Delete Me")
    deleted = db.delete_content(content["id"])
    assert deleted is True
    assert db.get_content(content["id"]) is None


def test_content_performance():
    content = db.create_content("Performance Test")
    db.record_engagement(content["id"], "x", impressions=1000, likes=50, comments=10, shares=5)
    db.record_engagement(content["id"], "x", impressions=500, likes=25, comments=5, shares=2)
    perf = db.get_content_performance(content["id"])
    assert perf["impressions"] == 1500
    assert perf["likes"] == 75
    assert perf["comments"] == 15
    assert perf["shares"] == 7
    assert perf["measurement_count"] == 2


# ---------------------------------------------------------------------------
# Influencers
# ---------------------------------------------------------------------------


def test_create_influencer():
    inf = db.create_influencer("@testuser", platform="x", name="Test User", followers=50000)
    assert inf["id"] > 0
    assert inf["handle"] == "@testuser"
    assert inf["followers"] == 50000
    assert inf["status"] == "discovered"


def test_list_influencers_by_niche():
    db.create_influencer("@tech1", niche="technology")
    db.create_influencer("@fashion1", niche="fashion")
    db.create_influencer("@tech2", niche="technology")
    tech = db.list_influencers(niche="technology")
    assert len(tech) == 2


def test_list_influencers_by_min_score():
    db.create_influencer("@low", relevance_score=20)
    db.create_influencer("@high", relevance_score=90)
    high_score = db.list_influencers(min_score=50)
    assert len(high_score) == 1
    assert high_score[0]["handle"] == "@high"


def test_update_influencer():
    inf = db.create_influencer("@update")
    updated = db.update_influencer(inf["id"], status="scored", relevance_score=85.5)
    assert updated["status"] == "scored"
    assert updated["relevance_score"] == 85.5


def test_influencer_roi():
    inf = db.create_influencer("@roi_test")
    c = db.create_campaign("ROI Campaign")
    db.create_influencer_campaign(inf["id"], c["id"], cost=500.0)
    db.record_conversion(influencer_id=inf["id"], campaign_id=c["id"], revenue=2000.0)
    roi = db.get_influencer_roi(inf["id"])
    assert roi["campaigns_count"] == 1
    assert roi["total_cost"] == 500.0
    assert roi["total_revenue"] == 2000.0
    assert roi["conversions"] == 1
    assert roi["roi_percent"] == 300.0


# ---------------------------------------------------------------------------
# Influencer Campaigns
# ---------------------------------------------------------------------------


def test_create_influencer_campaign():
    inf = db.create_influencer("@creator")
    c = db.create_campaign("Test")
    ic = db.create_influencer_campaign(inf["id"], c["id"], cost=300.0)
    assert ic["influencer_id"] == inf["id"]
    assert ic["campaign_id"] == c["id"]
    assert ic["cost"] == 300.0
    assert ic["status"] == "matched"


def test_list_influencer_campaigns():
    inf = db.create_influencer("@creator2")
    c = db.create_campaign("Test2")
    db.create_influencer_campaign(inf["id"], c["id"])
    result = db.list_influencer_campaigns(campaign_id=c["id"])
    assert len(result) == 1


def test_update_influencer_campaign():
    inf = db.create_influencer("@updater")
    c = db.create_campaign("Update Test")
    ic = db.create_influencer_campaign(inf["id"], c["id"])
    updated = db.update_influencer_campaign(ic["id"], status="active", cost=750.0)
    assert updated["status"] == "active"
    assert updated["cost"] == 750.0


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------


def test_create_asset():
    a = db.create_asset("Hero Image", asset_type="image", width=1200, height=675)
    assert a["id"] > 0
    assert a["name"] == "Hero Image"
    assert a["width"] == 1200
    assert a["height"] == 675
    assert a["status"] == "draft"


def test_list_assets_by_type():
    db.create_asset("Image 1", asset_type="image")
    db.create_asset("Video 1", asset_type="video")
    db.create_asset("Image 2", asset_type="image")
    images = db.list_assets(asset_type="image")
    assert len(images) == 2


def test_asset_variations():
    a = db.create_asset("Base", variations=[{"variant": "warm"}, {"variant": "cool"}])
    result = db.get_asset(a["id"])
    assert len(result["variations"]) == 2


def test_update_asset():
    a = db.create_asset("Update Me")
    updated = db.update_asset(a["id"], status="approved", file_path="/output.png")
    assert updated["status"] == "approved"
    assert updated["file_path"] == "/output.png"


# ---------------------------------------------------------------------------
# Engagements
# ---------------------------------------------------------------------------


def test_record_engagement():
    content = db.create_content("Engaged Post")
    e = db.record_engagement(content["id"], "x",
                             impressions=10000, likes=500, comments=100, shares=50, clicks=200)
    assert e["id"] > 0
    assert e["impressions"] == 10000
    assert e["likes"] == 500
    assert e["clicks"] == 200


def test_get_engagements_by_content():
    content = db.create_content("Multi-Engage")
    db.record_engagement(content["id"], "x", likes=10)
    db.record_engagement(content["id"], "instagram", likes=20)
    all_eng = db.get_engagements(content_id=content["id"])
    assert len(all_eng) == 2
    x_eng = db.get_engagements(content_id=content["id"], platform="x")
    assert len(x_eng) == 1


def test_engagement_sentiment():
    content = db.create_content("Sentiment Test")
    e = db.record_engagement(content["id"], "x", sentiment="positive")
    assert e["sentiment"] == "positive"


# ---------------------------------------------------------------------------
# Conversions
# ---------------------------------------------------------------------------


def test_record_conversion():
    conv = db.record_conversion(
        conversion_type="lead", value=100.0, revenue=500.0, source="organic"
    )
    assert conv["id"] > 0
    assert conv["conversion_type"] == "lead"
    assert conv["revenue"] == 500.0


def test_get_conversions_by_campaign():
    c = db.create_campaign("Conv Campaign")
    db.record_conversion(campaign_id=c["id"], conversion_type="lead")
    db.record_conversion(campaign_id=c["id"], conversion_type="sale")
    result = db.get_conversions(campaign_id=c["id"])
    assert len(result) == 2


def test_conversion_attribution():
    content = db.create_content("Attributed")
    conv = db.record_conversion(
        content_id=content["id"], conversion_type="sale",
        revenue=1000.0, attribution_model="last_touch", tracking_id="ext_123"
    )
    assert conv["tracking_id"] == "ext_123"
    assert conv["attribution_model"] == "last_touch"


# ---------------------------------------------------------------------------
# Schedules
# ---------------------------------------------------------------------------


def test_create_schedule():
    content = db.create_content("Scheduled Post")
    future = int(time.time()) + 86400
    s = db.create_schedule(content["id"], "x", future)
    assert s["content_id"] == content["id"]
    assert s["scheduled_at"] == future
    assert s["status"] == "pending"


def test_get_schedules():
    content = db.create_content("Schedule List")
    now = int(time.time())
    db.create_schedule(content["id"], "x", now)
    db.create_schedule(content["id"], "instagram", now + 3600)
    result = db.get_schedules(content_id=content["id"])
    assert len(result) == 2


def test_update_schedule():
    content = db.create_content("Update Schedule")
    s = db.create_schedule(content["id"], "x", int(time.time()))
    updated = db.update_schedule(s["id"], status="published", published_at=int(time.time()))
    assert updated["status"] == "published"
    assert updated["published_at"] is not None


# ---------------------------------------------------------------------------
# Video Pipeline
# ---------------------------------------------------------------------------


def test_create_video():
    v = db.create_video("Product Demo", brief="Show the product in action")
    assert v["id"] > 0
    assert v["title"] == "Product Demo"
    assert v["status"] == "brief"


def test_video_storyboard():
    v = db.create_video("Storyboard Test", storyboard={"scenes": [{"frame": 1, "desc": "intro"}]})
    result = db.get_video(v["id"])
    assert result["storyboard"]["scenes"][0]["desc"] == "intro"


def test_list_videos_by_status():
    db.create_video("Brief Video", status="brief")
    db.create_video("Rendered Video", status="exported")
    brief_vids = db.list_videos(status="brief")
    assert len(brief_vids) == 1


def test_update_video():
    v = db.create_video("Update Video")
    updated = db.update_video(v["id"], status="script", script="Scene 1: Opening...")
    assert updated["status"] == "script"
    assert updated["script"] == "Scene 1: Opening..."


def test_video_variations():
    v = db.create_video("Variations Test", variations=[
        {"platform": "tiktok", "aspect": "9:16"},
        {"platform": "instagram", "aspect": "1:1"},
    ])
    result = db.get_video(v["id"])
    assert len(result["variations"]) == 2


# ---------------------------------------------------------------------------
# Attribution
# ---------------------------------------------------------------------------


def test_record_attribution():
    a = db.record_attribution(
        channel="x", impressions=50000, clicks=1000,
        leads=50, conversions=10, revenue=5000.0, cost=1000.0
    )
    assert a["id"] > 0
    assert a["roi"] == 400.0  # ((5000 - 1000) / 1000) * 100


def test_attribution_roi_calculation():
    a = db.record_attribution(revenue=2000.0, cost=1000.0)
    assert a["roi"] == 100.0

    b = db.record_attribution(revenue=500.0, cost=1000.0)
    assert b["roi"] == -50.0

    c = db.record_attribution(revenue=0.0, cost=0.0)
    assert c["roi"] == 0.0


def test_get_attribution_by_campaign():
    c = db.create_campaign("Attr Campaign")
    db.record_attribution(campaign_id=c["id"], channel="x")
    db.record_attribution(campaign_id=c["id"], channel="instagram")
    result = db.get_attribution(campaign_id=c["id"])
    assert len(result) == 2


# ---------------------------------------------------------------------------
# Analytics / Reporting
# ---------------------------------------------------------------------------


def test_top_content():
    c1 = db.create_content("Popular")
    c2 = db.create_content("Less Popular")
    db.record_engagement(c1["id"], "x", likes=100, shares=50, clicks=200)
    db.record_engagement(c2["id"], "x", likes=10, shares=5, clicks=20)
    top = db.get_top_content(limit=5)
    assert len(top) >= 2
    assert top[0]["id"] == c1["id"]


def test_top_content_by_platform():
    c = db.create_content("Platform Specific", platform="instagram")
    db.record_engagement(c["id"], "instagram", likes=100)
    top = db.get_top_content(platform="instagram")
    assert len(top) == 1
    assert top[0]["platform"] == "instagram"


def test_campaign_summary_with_data():
    c = db.create_campaign("Full Campaign")
    content = db.create_content("Post 1", campaign_id=c["id"])
    db.record_engagement(content["id"], "x", impressions=5000, likes=200, clicks=50)
    db.record_conversion(campaign_id=c["id"], revenue=1000.0)
    db.record_attribution(campaign_id=c["id"], channel="x", cost=200.0)
    summary = db.get_campaign_summary(c["id"])
    assert summary["content_total"] == 1
    assert summary["impressions"] == 5000
    assert summary["conversions"] == 1
    assert summary["total_revenue"] == 1000.0
    assert summary["total_cost"] == 200.0
    assert summary["roi_percent"] == 400.0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_list_returns_empty():
    assert db.list_campaigns() == []
    assert db.list_content() == []
    assert db.list_influencers() == []
    assert db.list_assets() == []
    assert db.list_videos() == []


def test_update_nonexistent_returns_none():
    assert db.update_campaign(99999, name="x") is None
    assert db.update_content(99999, title="x") is None
    assert db.update_influencer(99999, handle="x") is None


def test_json_fields_round_trip():
    content = db.create_content("JSON RT", media_urls=["a", "b"], tags=["c", "d"])
    retrieved = db.get_content(content["id"])
    assert retrieved["media_urls"] == ["a", "b"]
    assert retrieved["tags"] == ["c", "d"]


def test_concurrent_access():
    """DB should handle basic concurrent reads/writes without error."""
    import threading
    db.reset_connection()
    errors = []

    def writer():
        try:
            for i in range(10):
                db.create_campaign(f"Concurrent {i}")
        except Exception as e:
            errors.append(e)

    def reader():
        try:
            for _ in range(10):
                db.list_campaigns()
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=writer) for _ in range(3)]
    threads += [threading.Thread(target=reader) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    campaigns = db.list_campaigns()
    assert len(campaigns) == 30
