"""SQLite-backed tracking database for the Guardian Media Farm system.

Tracks content, campaigns, influencers, assets, engagements, and ROI
across social, influencer, photo/creative, and video/media pipelines.

Database lives at ``<HERMES_HOME>/media_farm.db``.

Schema version: 1
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Generator, Optional

from hermes_constants import get_hermes_home

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS content (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    content_type    TEXT NOT NULL DEFAULT 'post',
    platform        TEXT NOT NULL DEFAULT '',
    campaign_id     INTEGER,
    status          TEXT NOT NULL DEFAULT 'idea',
    hook            TEXT DEFAULT '',
    script          TEXT DEFAULT '',
    body            TEXT DEFAULT '',
    media_urls      TEXT DEFAULT '[]',
    tags            TEXT DEFAULT '[]',
    scheduled_at    INTEGER,
    published_at    INTEGER,
    platform_post_id TEXT DEFAULT '',
    created_at      INTEGER NOT NULL,
    updated_at      INTEGER NOT NULL,
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
);

CREATE TABLE IF NOT EXISTS campaigns (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    campaign_type   TEXT NOT NULL DEFAULT 'social',
    objective       TEXT DEFAULT '',
    audience        TEXT DEFAULT '',
    platforms       TEXT DEFAULT '[]',
    start_date      TEXT DEFAULT '',
    end_date        TEXT DEFAULT '',
    cadence         TEXT DEFAULT '',
    voice           TEXT DEFAULT '',
    budget          REAL DEFAULT 0.0,
    status          TEXT NOT NULL DEFAULT 'draft',
    created_at      INTEGER NOT NULL,
    updated_at      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS influencers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    handle          TEXT NOT NULL,
    name            TEXT DEFAULT '',
    platform        TEXT NOT NULL DEFAULT '',
    followers       INTEGER DEFAULT 0,
    engagement_rate REAL DEFAULT 0.0,
    niche           TEXT DEFAULT '',
    relevance_score REAL DEFAULT 0.0,
    audience_demo   TEXT DEFAULT '{}',
    contact_info    TEXT DEFAULT '{}',
    status          TEXT NOT NULL DEFAULT 'discovered',
    notes           TEXT DEFAULT '',
    created_at      INTEGER NOT NULL,
    updated_at      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS influencer_campaigns (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    influencer_id   INTEGER NOT NULL,
    campaign_id     INTEGER NOT NULL,
    status          TEXT NOT NULL DEFAULT 'matched',
    outreach_sent   INTEGER,
    outreach_opened INTEGER,
    response_received INTEGER,
    deliverables    TEXT DEFAULT '[]',
    cost            REAL DEFAULT 0.0,
    content_ids     TEXT DEFAULT '[]',
    created_at      INTEGER NOT NULL,
    updated_at      INTEGER NOT NULL,
    FOREIGN KEY (influencer_id) REFERENCES influencers(id),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
);

CREATE TABLE IF NOT EXISTS assets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    asset_type      TEXT NOT NULL DEFAULT 'image',
    file_path       TEXT DEFAULT '',
    url             TEXT DEFAULT '',
    prompt          TEXT DEFAULT '',
    model           TEXT DEFAULT '',
    width           INTEGER DEFAULT 0,
    height          INTEGER DEFAULT 0,
    duration_secs   REAL DEFAULT 0.0,
    format          TEXT DEFAULT '',
    file_size       INTEGER DEFAULT 0,
    campaign_id     INTEGER,
    content_id      INTEGER,
    brief           TEXT DEFAULT '',
    variations      TEXT DEFAULT '[]',
    status          TEXT NOT NULL DEFAULT 'draft',
    tags            TEXT DEFAULT '[]',
    created_at      INTEGER NOT NULL,
    updated_at      INTEGER NOT NULL,
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id),
    FOREIGN KEY (content_id) REFERENCES content(id)
);

CREATE TABLE IF NOT EXISTS engagements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id      INTEGER NOT NULL,
    platform        TEXT NOT NULL,
    impressions     INTEGER DEFAULT 0,
    reach           INTEGER DEFAULT 0,
    likes           INTEGER DEFAULT 0,
    comments        INTEGER DEFAULT 0,
    shares          INTEGER DEFAULT 0,
    saves           INTEGER DEFAULT 0,
    clicks          INTEGER DEFAULT 0,
    video_views     INTEGER DEFAULT 0,
    watch_time_secs REAL DEFAULT 0.0,
    engagement_rate REAL DEFAULT 0.0,
    sentiment       TEXT DEFAULT 'neutral',
    measured_at     INTEGER NOT NULL,
    FOREIGN KEY (content_id) REFERENCES content(id)
);

CREATE TABLE IF NOT EXISTS conversions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id      INTEGER,
    campaign_id     INTEGER,
    influencer_id   INTEGER,
    conversion_type TEXT NOT NULL DEFAULT 'lead',
    value           REAL DEFAULT 0.0,
    revenue         REAL DEFAULT 0.0,
    source          TEXT DEFAULT '',
    attribution_model TEXT DEFAULT 'last_touch',
    tracking_id     TEXT DEFAULT '',
    created_at      INTEGER NOT NULL,
    FOREIGN KEY (content_id) REFERENCES content(id),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id),
    FOREIGN KEY (influencer_id) REFERENCES influencers(id)
);

CREATE TABLE IF NOT EXISTS schedules (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id      INTEGER NOT NULL,
    platform        TEXT NOT NULL,
    scheduled_at    INTEGER NOT NULL,
    published_at    INTEGER,
    status          TEXT NOT NULL DEFAULT 'pending',
    publish_url     TEXT DEFAULT '',
    error           TEXT DEFAULT '',
    retry_count     INTEGER DEFAULT 0,
    created_at      INTEGER NOT NULL,
    FOREIGN KEY (content_id) REFERENCES content(id)
);

CREATE TABLE IF NOT EXISTS video_pipeline (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    brief           TEXT DEFAULT '',
    script          TEXT DEFAULT '',
    storyboard      TEXT DEFAULT '{}',
    assets          TEXT DEFAULT '[]',
    video_path      TEXT DEFAULT '',
    export_path     TEXT DEFAULT '',
    variations      TEXT DEFAULT '[]',
    campaign_id     INTEGER,
    content_id      INTEGER,
    status          TEXT NOT NULL DEFAULT 'brief',
    duration_secs   REAL DEFAULT 0.0,
    resolution      TEXT DEFAULT '',
    created_at      INTEGER NOT NULL,
    updated_at      INTEGER NOT NULL,
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id),
    FOREIGN KEY (content_id) REFERENCES content(id)
);

CREATE TABLE IF NOT EXISTS attribution (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id     INTEGER,
    content_id      INTEGER,
    influencer_id   INTEGER,
    channel         TEXT NOT NULL DEFAULT '',
    impressions     INTEGER DEFAULT 0,
    clicks          INTEGER DEFAULT 0,
    leads           INTEGER DEFAULT 0,
    conversions     INTEGER DEFAULT 0,
    revenue         REAL DEFAULT 0.0,
    cost            REAL DEFAULT 0.0,
    roi             REAL DEFAULT 0.0,
    model           TEXT NOT NULL DEFAULT 'last_touch',
    period_start    TEXT DEFAULT '',
    period_end      TEXT DEFAULT '',
    created_at      INTEGER NOT NULL,
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id),
    FOREIGN KEY (content_id) REFERENCES content(id),
    FOREIGN KEY (influencer_id) REFERENCES influencers(id)
);

CREATE INDEX IF NOT EXISTS idx_content_campaign ON content(campaign_id);
CREATE INDEX IF NOT EXISTS idx_content_platform ON content(platform);
CREATE INDEX IF NOT EXISTS idx_content_status ON content(status);
CREATE INDEX IF NOT EXISTS idx_influencer_campaign_influencer ON influencer_campaigns(influencer_id);
CREATE INDEX IF NOT EXISTS idx_influencer_campaign_campaign ON influencer_campaigns(campaign_id);
CREATE INDEX IF NOT EXISTS idx_engagements_content ON engagements(content_id);
CREATE INDEX IF NOT EXISTS idx_conversions_content ON conversions(content_id);
CREATE INDEX IF NOT EXISTS idx_conversions_campaign ON conversions(campaign_id);
CREATE INDEX IF NOT EXISTS idx_schedules_content ON schedules(content_id);
CREATE INDEX IF NOT EXISTS idx_video_pipeline_campaign ON video_pipeline(campaign_id);
CREATE INDEX IF NOT EXISTS idx_attribution_campaign ON attribution(campaign_id);
CREATE INDEX IF NOT EXISTS idx_attribution_content ON attribution(content_id);
CREATE INDEX IF NOT EXISTS idx_assets_campaign ON assets(campaign_id);
"""

# ---------------------------------------------------------------------------
# Content status lifecycle
# ---------------------------------------------------------------------------

CONTENT_STATUSES = {
    "idea", "research", "trending", "hook", "scripted", "drafting",
    "created", "review", "approved", "scheduled", "published",
    "measuring", "optimised", "archived",
}

CAMPAIGN_STATUSES = {"draft", "active", "paused", "completed", "archived"}

INFLUENCER_STATUSES = {
    "discovered", "researched", "scored", "matched", "outreach_sent",
    "responded", "negotiating", "active", "completed", "archived",
}

ASSET_STATUSES = {"draft", "created", "variations", "approved", "published", "archived"}

VIDEO_STATUSES = {"brief", "script", "storyboard", "assets", "rendering", "review", "exported", "published", "archived"}

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Content:
    id: int = 0
    title: str = ""
    content_type: str = "post"
    platform: str = ""
    campaign_id: Optional[int] = None
    status: str = "idea"
    hook: str = ""
    script: str = ""
    body: str = ""
    media_urls: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    scheduled_at: Optional[int] = None
    published_at: Optional[int] = None
    platform_post_id: str = ""
    created_at: int = 0
    updated_at: int = 0


@dataclass
class Campaign:
    id: int = 0
    name: str = ""
    campaign_type: str = "social"
    objective: str = ""
    audience: str = ""
    platforms: list[str] = field(default_factory=list)
    start_date: str = ""
    end_date: str = ""
    cadence: str = ""
    voice: str = ""
    budget: float = 0.0
    status: str = "draft"
    created_at: int = 0
    updated_at: int = 0


@dataclass
class Influencer:
    id: int = 0
    handle: str = ""
    name: str = ""
    platform: str = ""
    followers: int = 0
    engagement_rate: float = 0.0
    niche: str = ""
    relevance_score: float = 0.0
    audience_demo: dict = field(default_factory=dict)
    contact_info: dict = field(default_factory=dict)
    status: str = "discovered"
    notes: str = ""
    created_at: int = 0
    updated_at: int = 0


@dataclass
class InfluencerCampaign:
    id: int = 0
    influencer_id: int = 0
    campaign_id: int = 0
    status: str = "matched"
    outreach_sent: Optional[int] = None
    outreach_opened: Optional[int] = None
    response_received: Optional[int] = None
    deliverables: list[dict] = field(default_factory=list)
    cost: float = 0.0
    content_ids: list[int] = field(default_factory=list)
    created_at: int = 0
    updated_at: int = 0


@dataclass
class Asset:
    id: int = 0
    name: str = ""
    asset_type: str = "image"
    file_path: str = ""
    url: str = ""
    prompt: str = ""
    model: str = ""
    width: int = 0
    height: int = 0
    duration_secs: float = 0.0
    format: str = ""
    file_size: int = 0
    campaign_id: Optional[int] = None
    content_id: Optional[int] = None
    brief: str = ""
    variations: list[dict] = field(default_factory=list)
    status: str = "draft"
    tags: list[str] = field(default_factory=list)
    created_at: int = 0
    updated_at: int = 0


@dataclass
class Engagement:
    id: int = 0
    content_id: int = 0
    platform: str = ""
    impressions: int = 0
    reach: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0
    clicks: int = 0
    video_views: int = 0
    watch_time_secs: float = 0.0
    engagement_rate: float = 0.0
    sentiment: str = "neutral"
    measured_at: int = 0


@dataclass
class Conversion:
    id: int = 0
    content_id: Optional[int] = None
    campaign_id: Optional[int] = None
    influencer_id: Optional[int] = None
    conversion_type: str = "lead"
    value: float = 0.0
    revenue: float = 0.0
    source: str = ""
    attribution_model: str = "last_touch"
    tracking_id: str = ""
    created_at: int = 0


@dataclass
class Schedule:
    id: int = 0
    content_id: int = 0
    platform: str = ""
    scheduled_at: int = 0
    published_at: Optional[int] = None
    status: str = "pending"
    publish_url: str = ""
    error: str = ""
    retry_count: int = 0
    created_at: int = 0


@dataclass
class VideoPipeline:
    id: int = 0
    title: str = ""
    brief: str = ""
    script: str = ""
    storyboard: dict = field(default_factory=dict)
    assets: list[dict] = field(default_factory=list)
    video_path: str = ""
    export_path: str = ""
    variations: list[dict] = field(default_factory=list)
    campaign_id: Optional[int] = None
    content_id: Optional[int] = None
    status: str = "brief"
    duration_secs: float = 0.0
    resolution: str = ""
    created_at: int = 0
    updated_at: int = 0


@dataclass
class AttributionRecord:
    id: int = 0
    campaign_id: Optional[int] = None
    content_id: Optional[int] = None
    influencer_id: Optional[int] = None
    channel: str = ""
    impressions: int = 0
    clicks: int = 0
    leads: int = 0
    conversions: int = 0
    revenue: float = 0.0
    cost: float = 0.0
    roi: float = 0.0
    model: str = "last_touch"
    period_start: str = ""
    period_end: str = ""
    created_at: int = 0


# ---------------------------------------------------------------------------
# Database connection
# ---------------------------------------------------------------------------

_local = threading.local()


def _db_path() -> Path:
    return get_hermes_home() / "media_farm.db"


def _connect() -> sqlite3.Connection:
    path = _db_path()
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _get_conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    conn_path = getattr(_local, "conn_path", None)
    if conn is None or conn_path != str(_db_path()):
        close_connection()
        conn = _connect()
        _local.conn = conn
        _local.conn_path = str(_db_path())
    return conn


def close_connection() -> None:
    """Close the cached thread-local connection (used by tests/introspection)."""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        with suppress(sqlite3.Error):
            conn.close()
        _local.conn = None
        _local.conn_path = None


def reset_connection() -> None:
    close_connection()


@contextmanager
def _transaction() -> Generator[sqlite3.Connection, None, None]:
    conn = _get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def init_db() -> None:
    """Create tables if they don't exist."""
    conn = _get_conn()
    conn.executescript(SCHEMA_SQL)
    conn.execute(
        "INSERT OR REPLACE INTO state_meta (key, value) VALUES (?, ?)",
        ("schema_version", str(SCHEMA_VERSION)),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------

def _now() -> int:
    return int(time.time())


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def _json_fields(*fields: str):
    """Decorator factory: parse JSON fields on the way out, serialize on the way in."""
    def wrapper(fn):
        fn._json_fields = fields
        return fn
    return wrapper


# --- Campaigns ---

def create_campaign(name: str, campaign_type: str = "social", **kwargs: Any) -> dict[str, Any]:
    now = _now()
    with _transaction() as conn:
        cur = conn.execute(
            """INSERT INTO campaigns (name, campaign_type, objective, audience,
               platforms, start_date, end_date, cadence, voice, budget, status,
               created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                name, campaign_type,
                kwargs.get("objective", ""),
                kwargs.get("audience", ""),
                json.dumps(kwargs.get("platforms", [])),
                kwargs.get("start_date", ""),
                kwargs.get("end_date", ""),
                kwargs.get("cadence", ""),
                kwargs.get("voice", ""),
                kwargs.get("budget", 0.0),
                kwargs.get("status", "draft"),
                now, now,
            ),
        )
        row_id = cur.lastrowid
    return get_campaign(row_id)


def get_campaign(campaign_id: int) -> Optional[dict[str, Any]]:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
    if row:
        d = _row_to_dict(row)
        d["platforms"] = json.loads(d["platforms"])
        return d
    return None


def list_campaigns(status: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
    conn = _get_conn()
    if status:
        rows = conn.execute(
            "SELECT * FROM campaigns WHERE status = ? ORDER BY created_at DESC LIMIT ?",
            (status, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM campaigns ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    results = []
    for row in rows:
        d = _row_to_dict(row)
        d["platforms"] = json.loads(d["platforms"])
        results.append(d)
    return results


def update_campaign(campaign_id: int, **kwargs: Any) -> Optional[dict[str, Any]]:
    now = _now()
    sets = ["updated_at = ?"]
    vals: list[Any] = [now]
    for key in ("name", "campaign_type", "objective", "audience", "start_date",
                 "end_date", "cadence", "voice", "budget", "status"):
        if key in kwargs:
            sets.append(f"{key} = ?")
            vals.append(kwargs[key])
    if "platforms" in kwargs:
        sets.append("platforms = ?")
        vals.append(json.dumps(kwargs["platforms"]))
    vals.append(campaign_id)
    with _transaction() as conn:
        conn.execute(f"UPDATE campaigns SET {', '.join(sets)} WHERE id = ?", vals)
    return get_campaign(campaign_id)


# --- Content ---

def create_content(title: str, content_type: str = "post", **kwargs: Any) -> dict[str, Any]:
    now = _now()
    with _transaction() as conn:
        cur = conn.execute(
            """INSERT INTO content (title, content_type, platform, campaign_id,
               status, hook, script, body, media_urls, tags, scheduled_at,
               published_at, platform_post_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                title, content_type,
                kwargs.get("platform", ""),
                kwargs.get("campaign_id"),
                kwargs.get("status", "idea"),
                kwargs.get("hook", ""),
                kwargs.get("script", ""),
                kwargs.get("body", ""),
                json.dumps(kwargs.get("media_urls", [])),
                json.dumps(kwargs.get("tags", [])),
                kwargs.get("scheduled_at"),
                kwargs.get("published_at"),
                kwargs.get("platform_post_id", ""),
                now, now,
            ),
        )
        row_id = cur.lastrowid
    return get_content(row_id)


def get_content(content_id: int) -> Optional[dict[str, Any]]:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM content WHERE id = ?", (content_id,)).fetchone()
    if row:
        d = _row_to_dict(row)
        d["media_urls"] = json.loads(d["media_urls"])
        d["tags"] = json.loads(d["tags"])
        return d
    return None


def list_content(
    status: Optional[str] = None,
    platform: Optional[str] = None,
    campaign_id: Optional[int] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    conn = _get_conn()
    conditions = []
    params: list[Any] = []
    if status:
        conditions.append("status = ?")
        params.append(status)
    if platform:
        conditions.append("platform = ?")
        params.append(platform)
    if campaign_id:
        conditions.append("campaign_id = ?")
        params.append(campaign_id)
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)
    rows = conn.execute(f"SELECT * FROM content{where} ORDER BY created_at DESC LIMIT ?", params).fetchall()
    results = []
    for row in rows:
        d = _row_to_dict(row)
        d["media_urls"] = json.loads(d["media_urls"])
        d["tags"] = json.loads(d["tags"])
        results.append(d)
    return results


def update_content(content_id: int, **kwargs: Any) -> Optional[dict[str, Any]]:
    now = _now()
    sets = ["updated_at = ?"]
    vals: list[Any] = [now]
    for key in ("title", "content_type", "platform", "campaign_id", "status",
                 "hook", "script", "body", "scheduled_at", "published_at", "platform_post_id"):
        if key in kwargs:
            sets.append(f"{key} = ?")
            vals.append(kwargs[key])
    for key in ("media_urls", "tags"):
        if key in kwargs:
            sets.append(f"{key} = ?")
            vals.append(json.dumps(kwargs[key]))
    vals.append(content_id)
    with _transaction() as conn:
        conn.execute(f"UPDATE content SET {', '.join(sets)} WHERE id = ?", vals)
    return get_content(content_id)


def delete_content(content_id: int) -> bool:
    with _transaction() as conn:
        cur = conn.execute("DELETE FROM content WHERE id = ?", (content_id,))
        return cur.rowcount > 0


# --- Influencers ---

def create_influencer(handle: str, platform: str = "", **kwargs: Any) -> dict[str, Any]:
    now = _now()
    with _transaction() as conn:
        cur = conn.execute(
            """INSERT INTO influencers (handle, name, platform, followers,
               engagement_rate, niche, relevance_score, audience_demo,
               contact_info, status, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                handle, kwargs.get("name", ""), platform,
                kwargs.get("followers", 0),
                kwargs.get("engagement_rate", 0.0),
                kwargs.get("niche", ""),
                kwargs.get("relevance_score", 0.0),
                json.dumps(kwargs.get("audience_demo", {})),
                json.dumps(kwargs.get("contact_info", {})),
                kwargs.get("status", "discovered"),
                kwargs.get("notes", ""),
                now, now,
            ),
        )
        row_id = cur.lastrowid
    return get_influencer(row_id)


def get_influencer(influencer_id: int) -> Optional[dict[str, Any]]:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM influencers WHERE id = ?", (influencer_id,)).fetchone()
    if row:
        d = _row_to_dict(row)
        d["audience_demo"] = json.loads(d["audience_demo"])
        d["contact_info"] = json.loads(d["contact_info"])
        return d
    return None


def list_influencers(
    status: Optional[str] = None,
    platform: Optional[str] = None,
    niche: Optional[str] = None,
    min_score: Optional[float] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    conn = _get_conn()
    conditions = []
    params: list[Any] = []
    if status:
        conditions.append("status = ?")
        params.append(status)
    if platform:
        conditions.append("platform = ?")
        params.append(platform)
    if niche:
        conditions.append("niche LIKE ?")
        params.append(f"%{niche}%")
    if min_score is not None:
        conditions.append("relevance_score >= ?")
        params.append(min_score)
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)
    rows = conn.execute(
        f"SELECT * FROM influencers{where} ORDER BY relevance_score DESC LIMIT ?", params
    ).fetchall()
    results = []
    for row in rows:
        d = _row_to_dict(row)
        d["audience_demo"] = json.loads(d["audience_demo"])
        d["contact_info"] = json.loads(d["contact_info"])
        results.append(d)
    return results


def update_influencer(influencer_id: int, **kwargs: Any) -> Optional[dict[str, Any]]:
    now = _now()
    sets = ["updated_at = ?"]
    vals: list[Any] = [now]
    for key in ("handle", "name", "platform", "followers", "engagement_rate",
                 "niche", "relevance_score", "status", "notes"):
        if key in kwargs:
            sets.append(f"{key} = ?")
            vals.append(kwargs[key])
    for key in ("audience_demo", "contact_info"):
        if key in kwargs:
            sets.append(f"{key} = ?")
            vals.append(json.dumps(kwargs[key]))
    vals.append(influencer_id)
    with _transaction() as conn:
        conn.execute(f"UPDATE influencers SET {', '.join(sets)} WHERE id = ?", vals)
    return get_influencer(influencer_id)


# --- Influencer Campaigns ---

def create_influencer_campaign(influencer_id: int, campaign_id: int, **kwargs: Any) -> dict[str, Any]:
    now = _now()
    with _transaction() as conn:
        cur = conn.execute(
            """INSERT INTO influencer_campaigns (influencer_id, campaign_id,
               status, outreach_sent, outreach_opened, response_received,
               deliverables, cost, content_ids, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                influencer_id, campaign_id,
                kwargs.get("status", "matched"),
                kwargs.get("outreach_sent"),
                kwargs.get("outreach_opened"),
                kwargs.get("response_received"),
                json.dumps(kwargs.get("deliverables", [])),
                kwargs.get("cost", 0.0),
                json.dumps(kwargs.get("content_ids", [])),
                now, now,
            ),
        )
        row_id = cur.lastrowid
    return _get_influencer_campaign(row_id)


def _get_influencer_campaign(ic_id: int) -> Optional[dict[str, Any]]:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM influencer_campaigns WHERE id = ?", (ic_id,)).fetchone()
    if row:
        d = _row_to_dict(row)
        d["deliverables"] = json.loads(d["deliverables"])
        d["content_ids"] = json.loads(d["content_ids"])
        return d
    return None


def list_influencer_campaigns(
    campaign_id: Optional[int] = None,
    influencer_id: Optional[int] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    conn = _get_conn()
    conditions = []
    params: list[Any] = []
    if campaign_id:
        conditions.append("campaign_id = ?")
        params.append(campaign_id)
    if influencer_id:
        conditions.append("influencer_id = ?")
        params.append(influencer_id)
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)
    rows = conn.execute(
        f"SELECT * FROM influencer_campaigns{where} ORDER BY created_at DESC LIMIT ?", params
    ).fetchall()
    results = []
    for row in rows:
        d = _row_to_dict(row)
        d["deliverables"] = json.loads(d["deliverables"])
        d["content_ids"] = json.loads(d["content_ids"])
        results.append(d)
    return results


def update_influencer_campaign(ic_id: int, **kwargs: Any) -> Optional[dict[str, Any]]:
    now = _now()
    sets = ["updated_at = ?"]
    vals: list[Any] = [now]
    for key in ("status", "outreach_sent", "outreach_opened", "response_received", "cost"):
        if key in kwargs:
            sets.append(f"{key} = ?")
            vals.append(kwargs[key])
    for key in ("deliverables", "content_ids"):
        if key in kwargs:
            sets.append(f"{key} = ?")
            vals.append(json.dumps(kwargs[key]))
    vals.append(ic_id)
    with _transaction() as conn:
        conn.execute(f"UPDATE influencer_campaigns SET {', '.join(sets)} WHERE id = ?", vals)
    return _get_influencer_campaign(ic_id)


# --- Assets ---

def create_asset(name: str, asset_type: str = "image", **kwargs: Any) -> dict[str, Any]:
    now = _now()
    with _transaction() as conn:
        cur = conn.execute(
            """INSERT INTO assets (name, asset_type, file_path, url, prompt,
               model, width, height, duration_secs, format, file_size,
               campaign_id, content_id, brief, variations, status, tags,
               created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                name, asset_type,
                kwargs.get("file_path", ""),
                kwargs.get("url", ""),
                kwargs.get("prompt", ""),
                kwargs.get("model", ""),
                kwargs.get("width", 0),
                kwargs.get("height", 0),
                kwargs.get("duration_secs", 0.0),
                kwargs.get("format", ""),
                kwargs.get("file_size", 0),
                kwargs.get("campaign_id"),
                kwargs.get("content_id"),
                kwargs.get("brief", ""),
                json.dumps(kwargs.get("variations", [])),
                kwargs.get("status", "draft"),
                json.dumps(kwargs.get("tags", [])),
                now, now,
            ),
        )
        row_id = cur.lastrowid
    return get_asset(row_id)


def get_asset(asset_id: int) -> Optional[dict[str, Any]]:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
    if row:
        d = _row_to_dict(row)
        d["variations"] = json.loads(d["variations"])
        d["tags"] = json.loads(d["tags"])
        return d
    return None


def list_assets(
    asset_type: Optional[str] = None,
    campaign_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    conn = _get_conn()
    conditions = []
    params: list[Any] = []
    if asset_type:
        conditions.append("asset_type = ?")
        params.append(asset_type)
    if campaign_id:
        conditions.append("campaign_id = ?")
        params.append(campaign_id)
    if status:
        conditions.append("status = ?")
        params.append(status)
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)
    rows = conn.execute(f"SELECT * FROM assets{where} ORDER BY created_at DESC LIMIT ?", params).fetchall()
    results = []
    for row in rows:
        d = _row_to_dict(row)
        d["variations"] = json.loads(d["variations"])
        d["tags"] = json.loads(d["tags"])
        results.append(d)
    return results


def update_asset(asset_id: int, **kwargs: Any) -> Optional[dict[str, Any]]:
    now = _now()
    sets = ["updated_at = ?"]
    vals: list[Any] = [now]
    for key in ("name", "asset_type", "file_path", "url", "prompt", "model",
                 "width", "height", "duration_secs", "format", "file_size",
                 "campaign_id", "content_id", "brief", "status"):
        if key in kwargs:
            sets.append(f"{key} = ?")
            vals.append(kwargs[key])
    for key in ("variations", "tags"):
        if key in kwargs:
            sets.append(f"{key} = ?")
            vals.append(json.dumps(kwargs[key]))
    vals.append(asset_id)
    with _transaction() as conn:
        conn.execute(f"UPDATE assets SET {', '.join(sets)} WHERE id = ?", vals)
    return get_asset(asset_id)


# --- Engagements ---

def record_engagement(content_id: int, platform: str, **kwargs: Any) -> dict[str, Any]:
    now = _now()
    with _transaction() as conn:
        cur = conn.execute(
            """INSERT INTO engagements (content_id, platform, impressions, reach,
               likes, comments, shares, saves, clicks, video_views,
               watch_time_secs, engagement_rate, sentiment, measured_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                content_id, platform,
                kwargs.get("impressions", 0),
                kwargs.get("reach", 0),
                kwargs.get("likes", 0),
                kwargs.get("comments", 0),
                kwargs.get("shares", 0),
                kwargs.get("saves", 0),
                kwargs.get("clicks", 0),
                kwargs.get("video_views", 0),
                kwargs.get("watch_time_secs", 0.0),
                kwargs.get("engagement_rate", 0.0),
                kwargs.get("sentiment", "neutral"),
                now,
            ),
        )
        row_id = cur.lastrowid
    conn = _get_conn()
    row = conn.execute("SELECT * FROM engagements WHERE id = ?", (row_id,)).fetchone()
    return _row_to_dict(row)


def get_engagements(
    content_id: Optional[int] = None,
    platform: Optional[str] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    conn = _get_conn()
    conditions = []
    params: list[Any] = []
    if content_id:
        conditions.append("content_id = ?")
        params.append(content_id)
    if platform:
        conditions.append("platform = ?")
        params.append(platform)
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)
    rows = conn.execute(f"SELECT * FROM engagements{where} ORDER BY measured_at DESC LIMIT ?", params).fetchall()
    return [_row_to_dict(r) for r in rows]


# --- Conversions ---

def record_conversion(**kwargs: Any) -> dict[str, Any]:
    now = _now()
    with _transaction() as conn:
        cur = conn.execute(
            """INSERT INTO conversions (content_id, campaign_id, influencer_id,
               conversion_type, value, revenue, source, attribution_model,
               tracking_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                kwargs.get("content_id"),
                kwargs.get("campaign_id"),
                kwargs.get("influencer_id"),
                kwargs.get("conversion_type", "lead"),
                kwargs.get("value", 0.0),
                kwargs.get("revenue", 0.0),
                kwargs.get("source", ""),
                kwargs.get("attribution_model", "last_touch"),
                kwargs.get("tracking_id", ""),
                now,
            ),
        )
        row_id = cur.lastrowid
    conn = _get_conn()
    row = conn.execute("SELECT * FROM conversions WHERE id = ?", (row_id,)).fetchone()
    return _row_to_dict(row)


def get_conversions(
    campaign_id: Optional[int] = None,
    content_id: Optional[int] = None,
    influencer_id: Optional[int] = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    conn = _get_conn()
    conditions = []
    params: list[Any] = []
    if campaign_id:
        conditions.append("campaign_id = ?")
        params.append(campaign_id)
    if content_id:
        conditions.append("content_id = ?")
        params.append(content_id)
    if influencer_id:
        conditions.append("influencer_id = ?")
        params.append(influencer_id)
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)
    rows = conn.execute(f"SELECT * FROM conversions{where} ORDER BY created_at DESC LIMIT ?", params).fetchall()
    return [_row_to_dict(r) for r in rows]


# --- Schedules ---

def create_schedule(content_id: int, platform: str, scheduled_at: int, **kwargs: Any) -> dict[str, Any]:
    now = _now()
    with _transaction() as conn:
        cur = conn.execute(
            """INSERT INTO schedules (content_id, platform, scheduled_at,
               published_at, status, publish_url, error, retry_count, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                content_id, platform, scheduled_at,
                kwargs.get("published_at"),
                kwargs.get("status", "pending"),
                kwargs.get("publish_url", ""),
                kwargs.get("error", ""),
                kwargs.get("retry_count", 0),
                now,
            ),
        )
        row_id = cur.lastrowid
    conn = _get_conn()
    row = conn.execute("SELECT * FROM schedules WHERE id = ?", (row_id,)).fetchone()
    return _row_to_dict(row)


def get_schedules(
    content_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    conn = _get_conn()
    conditions = []
    params: list[Any] = []
    if content_id:
        conditions.append("content_id = ?")
        params.append(content_id)
    if status:
        conditions.append("status = ?")
        params.append(status)
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)
    rows = conn.execute(f"SELECT * FROM schedules{where} ORDER BY scheduled_at ASC LIMIT ?", params).fetchall()
    return [_row_to_dict(r) for r in rows]


def update_schedule(schedule_id: int, **kwargs: Any) -> dict[str, Any]:
    with _transaction() as conn:
        sets = []
        vals: list[Any] = []
        for key in ("published_at", "status", "publish_url", "error", "retry_count"):
            if key in kwargs:
                sets.append(f"{key} = ?")
                vals.append(kwargs[key])
        if not sets:
            conn = _get_conn()
            row = conn.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
            return _row_to_dict(row) if row else {}
        vals.append(schedule_id)
        conn.execute(f"UPDATE schedules SET {', '.join(sets)} WHERE id = ?", vals)
    conn = _get_conn()
    row = conn.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
    return _row_to_dict(row) if row else {}


# --- Video Pipeline ---

def create_video(title: str, **kwargs: Any) -> dict[str, Any]:
    now = _now()
    with _transaction() as conn:
        cur = conn.execute(
            """INSERT INTO video_pipeline (title, brief, script, storyboard,
               assets, video_path, export_path, variations, campaign_id,
               content_id, status, duration_secs, resolution, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                title,
                kwargs.get("brief", ""),
                kwargs.get("script", ""),
                json.dumps(kwargs.get("storyboard", {})),
                json.dumps(kwargs.get("assets", [])),
                kwargs.get("video_path", ""),
                kwargs.get("export_path", ""),
                json.dumps(kwargs.get("variations", [])),
                kwargs.get("campaign_id"),
                kwargs.get("content_id"),
                kwargs.get("status", "brief"),
                kwargs.get("duration_secs", 0.0),
                kwargs.get("resolution", ""),
                now, now,
            ),
        )
        row_id = cur.lastrowid
    return get_video(row_id)


def get_video(video_id: int) -> Optional[dict[str, Any]]:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM video_pipeline WHERE id = ?", (video_id,)).fetchone()
    if row:
        d = _row_to_dict(row)
        d["storyboard"] = json.loads(d["storyboard"])
        d["assets"] = json.loads(d["assets"])
        d["variations"] = json.loads(d["variations"])
        return d
    return None


def list_videos(
    status: Optional[str] = None,
    campaign_id: Optional[int] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    conn = _get_conn()
    conditions = []
    params: list[Any] = []
    if status:
        conditions.append("status = ?")
        params.append(status)
    if campaign_id:
        conditions.append("campaign_id = ?")
        params.append(campaign_id)
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)
    rows = conn.execute(f"SELECT * FROM video_pipeline{where} ORDER BY created_at DESC LIMIT ?", params).fetchall()
    results = []
    for row in rows:
        d = _row_to_dict(row)
        d["storyboard"] = json.loads(d["storyboard"])
        d["assets"] = json.loads(d["assets"])
        d["variations"] = json.loads(d["variations"])
        results.append(d)
    return results


def update_video(video_id: int, **kwargs: Any) -> Optional[dict[str, Any]]:
    now = _now()
    sets = ["updated_at = ?"]
    vals: list[Any] = [now]
    for key in ("title", "brief", "script", "video_path", "export_path",
                 "campaign_id", "content_id", "status", "duration_secs", "resolution"):
        if key in kwargs:
            sets.append(f"{key} = ?")
            vals.append(kwargs[key])
    for key in ("storyboard", "assets", "variations"):
        if key in kwargs:
            sets.append(f"{key} = ?")
            vals.append(json.dumps(kwargs[key]))
    vals.append(video_id)
    with _transaction() as conn:
        conn.execute(f"UPDATE video_pipeline SET {', '.join(sets)} WHERE id = ?", vals)
    return get_video(video_id)


# --- Attribution ---

def record_attribution(**kwargs: Any) -> dict[str, Any]:
    now = _now()
    cost = kwargs.get("cost", 0.0)
    revenue = kwargs.get("revenue", 0.0)
    roi = ((revenue - cost) / cost * 100) if cost > 0 else 0.0
    with _transaction() as conn:
        cur = conn.execute(
            """INSERT INTO attribution (campaign_id, content_id, influencer_id,
               channel, impressions, clicks, leads, conversions, revenue, cost,
               roi, model, period_start, period_end, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                kwargs.get("campaign_id"),
                kwargs.get("content_id"),
                kwargs.get("influencer_id"),
                kwargs.get("channel", ""),
                kwargs.get("impressions", 0),
                kwargs.get("clicks", 0),
                kwargs.get("leads", 0),
                kwargs.get("conversions", 0),
                revenue, cost, roi,
                kwargs.get("model", "last_touch"),
                kwargs.get("period_start", ""),
                kwargs.get("period_end", ""),
                now,
            ),
        )
        row_id = cur.lastrowid
    conn = _get_conn()
    row = conn.execute("SELECT * FROM attribution WHERE id = ?", (row_id,)).fetchone()
    return _row_to_dict(row)


def get_attribution(
    campaign_id: Optional[int] = None,
    content_id: Optional[int] = None,
    influencer_id: Optional[int] = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    conn = _get_conn()
    conditions = []
    params: list[Any] = []
    if campaign_id:
        conditions.append("campaign_id = ?")
        params.append(campaign_id)
    if content_id:
        conditions.append("content_id = ?")
        params.append(content_id)
    if influencer_id:
        conditions.append("influencer_id = ?")
        params.append(influencer_id)
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)
    rows = conn.execute(f"SELECT * FROM attribution{where} ORDER BY created_at DESC LIMIT ?", params).fetchall()
    return [_row_to_dict(r) for r in rows]


# --- Analytics / Reporting ---

def get_campaign_summary(campaign_id: int) -> dict[str, Any]:
    """Aggregate summary for a campaign."""
    conn = _get_conn()
    content_count = conn.execute(
        "SELECT COUNT(*) FROM content WHERE campaign_id = ?", (campaign_id,)
    ).fetchone()[0]
    published_count = conn.execute(
        "SELECT COUNT(*) FROM content WHERE campaign_id = ? AND status = 'published'",
        (campaign_id,),
    ).fetchone()[0]

    engagement_row = conn.execute(
        """SELECT COALESCE(SUM(e.impressions), 0) as impressions,
                  COALESCE(SUM(e.reach), 0) as reach,
                  COALESCE(SUM(e.likes), 0) as likes,
                  COALESCE(SUM(e.comments), 0) as comments,
                  COALESCE(SUM(e.shares), 0) as shares,
                  COALESCE(SUM(e.clicks), 0) as clicks,
                  COALESCE(SUM(e.video_views), 0) as video_views
           FROM engagements e
           JOIN content c ON e.content_id = c.id
           WHERE c.campaign_id = ?""",
        (campaign_id,),
    ).fetchone()

    conversion_row = conn.execute(
        """SELECT COALESCE(SUM(value), 0) as total_value,
                  COALESCE(SUM(revenue), 0) as total_revenue,
                  COUNT(*) as conversion_count
           FROM conversions WHERE campaign_id = ?""",
        (campaign_id,),
    ).fetchone()

    cost_row = conn.execute(
        """SELECT COALESCE(SUM(cost), 0) as total_cost
           FROM attribution WHERE campaign_id = ?""",
        (campaign_id,),
    ).fetchone()

    influencer_count = conn.execute(
        "SELECT COUNT(*) FROM influencer_campaigns WHERE campaign_id = ?",
        (campaign_id,),
    ).fetchone()[0]

    total_cost = cost_row["total_cost"] if cost_row else 0.0
    total_revenue = conversion_row["total_revenue"] if conversion_row else 0.0
    roi = ((total_revenue - total_cost) / total_cost * 100) if total_cost > 0 else 0.0

    return {
        "campaign_id": campaign_id,
        "content_total": content_count,
        "content_published": published_count,
        "impressions": engagement_row["impressions"] if engagement_row else 0,
        "reach": engagement_row["reach"] if engagement_row else 0,
        "likes": engagement_row["likes"] if engagement_row else 0,
        "comments": engagement_row["comments"] if engagement_row else 0,
        "shares": engagement_row["shares"] if engagement_row else 0,
        "clicks": engagement_row["clicks"] if engagement_row else 0,
        "video_views": engagement_row["video_views"] if engagement_row else 0,
        "conversions": conversion_row["conversion_count"] if conversion_row else 0,
        "total_revenue": total_revenue,
        "total_cost": total_cost,
        "roi_percent": round(roi, 2),
        "influencers": influencer_count,
    }


def get_content_performance(content_id: int) -> dict[str, Any]:
    """Get aggregated engagement metrics for a piece of content."""
    conn = _get_conn()
    row = conn.execute(
        """SELECT COALESCE(SUM(impressions), 0) as impressions,
                  COALESCE(SUM(reach), 0) as reach,
                  COALESCE(SUM(likes), 0) as likes,
                  COALESCE(SUM(comments), 0) as comments,
                  COALESCE(SUM(shares), 0) as shares,
                  COALESCE(SUM(saves), 0) as saves,
                  COALESCE(SUM(clicks), 0) as clicks,
                  COALESCE(SUM(video_views), 0) as video_views,
                  COUNT(*) as measurement_count
           FROM engagements WHERE content_id = ?""",
        (content_id,),
    ).fetchone()
    conv_row = conn.execute(
        """SELECT COALESCE(SUM(revenue), 0) as revenue,
                  COUNT(*) as conversions
           FROM conversions WHERE content_id = ?""",
        (content_id,),
    ).fetchone()
    return {
        "content_id": content_id,
        "impressions": row["impressions"],
        "reach": row["reach"],
        "likes": row["likes"],
        "comments": row["comments"],
        "shares": row["shares"],
        "saves": row["saves"],
        "clicks": row["clicks"],
        "video_views": row["video_views"],
        "measurement_count": row["measurement_count"],
        "revenue": conv_row["revenue"],
        "conversions": conv_row["conversions"],
    }


def get_influencer_roi(influencer_id: int) -> dict[str, Any]:
    """ROI summary for an influencer across all campaigns."""
    conn = _get_conn()
    campaigns = conn.execute(
        "SELECT * FROM influencer_campaigns WHERE influencer_id = ?",
        (influencer_id,),
    ).fetchall()
    total_cost = sum(c["cost"] for c in campaigns)
    conv_row = conn.execute(
        """SELECT COALESCE(SUM(revenue), 0) as total_revenue,
                  COUNT(*) as conversions
           FROM conversions WHERE influencer_id = ?""",
        (influencer_id,),
    ).fetchone()
    total_revenue = conv_row["total_revenue"]
    roi = ((total_revenue - total_cost) / total_cost * 100) if total_cost > 0 else 0.0
    return {
        "influencer_id": influencer_id,
        "campaigns_count": len(campaigns),
        "total_cost": total_cost,
        "total_revenue": total_revenue,
        "conversions": conv_row["conversions"],
        "roi_percent": round(roi, 2),
    }


def get_top_content(limit: int = 10, platform: Optional[str] = None) -> list[dict[str, Any]]:
    """Top content by engagement."""
    conn = _get_conn()
    if platform:
        rows = conn.execute(
            """SELECT c.id, c.title, c.platform, c.status,
                      COALESCE(SUM(e.impressions), 0) as impressions,
                      COALESCE(SUM(e.likes), 0) as likes,
                      COALESCE(SUM(e.shares), 0) as shares,
                      COALESCE(SUM(e.clicks), 0) as clicks
               FROM content c
               LEFT JOIN engagements e ON c.id = e.content_id
               WHERE c.platform = ?
               GROUP BY c.id
               ORDER BY (likes + shares + clicks) DESC
               LIMIT ?""",
            (platform, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT c.id, c.title, c.platform, c.status,
                      COALESCE(SUM(e.impressions), 0) as impressions,
                      COALESCE(SUM(e.likes), 0) as likes,
                      COALESCE(SUM(e.shares), 0) as shares,
                      COALESCE(SUM(e.clicks), 0) as clicks
               FROM content c
               LEFT JOIN engagements e ON c.id = e.content_id
               GROUP BY c.id
               ORDER BY (likes + shares + clicks) DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


# --- state_meta (needed for schema versioning) ---

def _ensure_state_meta() -> None:
    conn = _get_conn()
    conn.execute(
        "CREATE TABLE IF NOT EXISTS state_meta (key TEXT PRIMARY KEY, value TEXT)"
    )
    conn.commit()


# Patch init_db to include state_meta
_original_init_db = init_db

def init_db() -> None:
    _ensure_state_meta()
    _original_init_db()
