"""Media Farm tool — core Hermes tool for the Guardian Media Farm system.

Provides a unified interface for managing content, campaigns, influencers,
assets, engagements, conversions, schedules, video pipelines, and
attribution tracking.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from tools.registry import registry

# Lazy import to avoid startup cost
_db = None


def _get_db():
    global _db
    if _db is None:
        from tools import media_farm_db as db_mod
        db_mod.init_db()
        _db = db_mod
    return _db


def _handle_media_farm(args: dict[str, Any], **_kw: Any) -> str:
    action = args.get("action", "")

    try:
        if action == "create_campaign":
            return _create_campaign(args)
        elif action == "list_campaigns":
            return _list_campaigns(args)
        elif action == "get_campaign":
            return _get_campaign(args)
        elif action == "update_campaign":
            return _update_campaign(args)
        elif action == "campaign_summary":
            return _campaign_summary(args)

        elif action == "create_content":
            return _create_content(args)
        elif action == "list_content":
            return _list_content(args)
        elif action == "get_content":
            return _get_content(args)
        elif action == "update_content":
            return _update_content(args)
        elif action == "delete_content":
            return _delete_content(args)
        elif action == "content_performance":
            return _content_performance(args)

        elif action == "create_influencer":
            return _create_influencer(args)
        elif action == "list_influencers":
            return _list_influencers(args)
        elif action == "get_influencer":
            return _get_influencer(args)
        elif action == "update_influencer":
            return _update_influencer(args)
        elif action == "influencer_roi":
            return _influencer_roi(args)

        elif action == "create_influencer_campaign":
            return _create_influencer_campaign(args)
        elif action == "list_influencer_campaigns":
            return _list_influencer_campaigns(args)
        elif action == "update_influencer_campaign":
            return _update_influencer_campaign(args)

        elif action == "create_asset":
            return _create_asset(args)
        elif action == "list_assets":
            return _list_assets(args)
        elif action == "get_asset":
            return _get_asset(args)
        elif action == "update_asset":
            return _update_asset(args)

        elif action == "record_engagement":
            return _record_engagement(args)
        elif action == "get_engagements":
            return _get_engagements(args)

        elif action == "record_conversion":
            return _record_conversion(args)
        elif action == "get_conversions":
            return _get_conversions(args)

        elif action == "create_schedule":
            return _create_schedule(args)
        elif action == "get_schedules":
            return _get_schedules(args)
        elif action == "update_schedule":
            return _update_schedule(args)

        elif action == "create_video":
            return _create_video(args)
        elif action == "list_videos":
            return _list_videos(args)
        elif action == "get_video":
            return _get_video(args)
        elif action == "update_video":
            return _update_video(args)

        elif action == "record_attribution":
            return _record_attribution(args)
        elif action == "get_attribution":
            return _get_attribution(args)

        elif action == "top_content":
            return _top_content(args)

        else:
            return json.dumps({"error": f"Unknown action: {action}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# --- Campaign handlers ---

def _create_campaign(args: dict) -> str:
    db = _get_db()
    result = db.create_campaign(
        name=args.get("name", "Untitled Campaign"),
        campaign_type=args.get("campaign_type", "social"),
        objective=args.get("objective", ""),
        audience=args.get("audience", ""),
        platforms=args.get("platforms", []),
        start_date=args.get("start_date", ""),
        end_date=args.get("end_date", ""),
        cadence=args.get("cadence", ""),
        voice=args.get("voice", ""),
        budget=args.get("budget", 0.0),
    )
    return json.dumps({"success": True, "campaign": result})


def _list_campaigns(args: dict) -> str:
    db = _get_db()
    result = db.list_campaigns(
        status=args.get("status"),
        limit=args.get("limit", 50),
    )
    return json.dumps({"success": True, "campaigns": result, "count": len(result)})


def _get_campaign(args: dict) -> str:
    db = _get_db()
    result = db.get_campaign(args.get("campaign_id", 0))
    if result is None:
        return json.dumps({"error": "Campaign not found"})
    return json.dumps({"success": True, "campaign": result})


def _update_campaign(args: dict) -> str:
    db = _get_db()
    campaign_id = args.get("campaign_id", 0)
    updates = {}
    for key in ("name", "campaign_type", "objective", "audience", "platforms",
                 "start_date", "end_date", "cadence", "voice", "budget", "status"):
        if key in args:
            updates[key] = args[key]
    result = db.update_campaign(campaign_id, **updates)
    return json.dumps({"success": True, "campaign": result})


def _campaign_summary(args: dict) -> str:
    db = _get_db()
    result = db.get_campaign_summary(args.get("campaign_id", 0))
    return json.dumps({"success": True, "summary": result})


# --- Content handlers ---

def _create_content(args: dict) -> str:
    db = _get_db()
    result = db.create_content(
        title=args.get("title", "Untitled Content"),
        content_type=args.get("content_type", "post"),
        platform=args.get("platform", ""),
        campaign_id=args.get("campaign_id"),
        status=args.get("status", "idea"),
        hook=args.get("hook", ""),
        script=args.get("script", ""),
        body=args.get("body", ""),
        media_urls=args.get("media_urls", []),
        tags=args.get("tags", []),
        scheduled_at=args.get("scheduled_at"),
        platform_post_id=args.get("platform_post_id", ""),
    )
    return json.dumps({"success": True, "content": result})


def _list_content(args: dict) -> str:
    db = _get_db()
    result = db.list_content(
        status=args.get("status"),
        platform=args.get("platform"),
        campaign_id=args.get("campaign_id"),
        limit=args.get("limit", 50),
    )
    return json.dumps({"success": True, "content": result, "count": len(result)})


def _get_content(args: dict) -> str:
    db = _get_db()
    result = db.get_content(args.get("content_id", 0))
    if result is None:
        return json.dumps({"error": "Content not found"})
    return json.dumps({"success": True, "content": result})


def _update_content(args: dict) -> str:
    db = _get_db()
    content_id = args.get("content_id", 0)
    updates = {}
    for key in ("title", "content_type", "platform", "campaign_id", "status",
                 "hook", "script", "body", "media_urls", "tags",
                 "scheduled_at", "published_at", "platform_post_id"):
        if key in args:
            updates[key] = args[key]
    result = db.update_content(content_id, **updates)
    return json.dumps({"success": True, "content": result})


def _delete_content(args: dict) -> str:
    db = _get_db()
    deleted = db.delete_content(args.get("content_id", 0))
    return json.dumps({"success": deleted, "deleted": deleted})


def _content_performance(args: dict) -> str:
    db = _get_db()
    result = db.get_content_performance(args.get("content_id", 0))
    return json.dumps({"success": True, "performance": result})


# --- Influencer handlers ---

def _create_influencer(args: dict) -> str:
    db = _get_db()
    result = db.create_influencer(
        handle=args.get("handle", ""),
        platform=args.get("platform", ""),
        name=args.get("name", ""),
        followers=args.get("followers", 0),
        engagement_rate=args.get("engagement_rate", 0.0),
        niche=args.get("niche", ""),
        relevance_score=args.get("relevance_score", 0.0),
        audience_demo=args.get("audience_demo", {}),
        contact_info=args.get("contact_info", {}),
        status=args.get("status", "discovered"),
        notes=args.get("notes", ""),
    )
    return json.dumps({"success": True, "influencer": result})


def _list_influencers(args: dict) -> str:
    db = _get_db()
    result = db.list_influencers(
        status=args.get("status"),
        platform=args.get("platform"),
        niche=args.get("niche"),
        min_score=args.get("min_score"),
        limit=args.get("limit", 50),
    )
    return json.dumps({"success": True, "influencers": result, "count": len(result)})


def _get_influencer(args: dict) -> str:
    db = _get_db()
    result = db.get_influencer(args.get("influencer_id", 0))
    if result is None:
        return json.dumps({"error": "Influencer not found"})
    return json.dumps({"success": True, "influencer": result})


def _update_influencer(args: dict) -> str:
    db = _get_db()
    influencer_id = args.get("influencer_id", 0)
    updates = {}
    for key in ("handle", "name", "platform", "followers", "engagement_rate",
                 "niche", "relevance_score", "status", "notes",
                 "audience_demo", "contact_info"):
        if key in args:
            updates[key] = args[key]
    result = db.update_influencer(influencer_id, **updates)
    return json.dumps({"success": True, "influencer": result})


def _influencer_roi(args: dict) -> str:
    db = _get_db()
    result = db.get_influencer_roi(args.get("influencer_id", 0))
    return json.dumps({"success": True, "roi": result})


# --- Influencer Campaign handlers ---

def _create_influencer_campaign(args: dict) -> str:
    db = _get_db()
    result = db.create_influencer_campaign(
        influencer_id=args.get("influencer_id", 0),
        campaign_id=args.get("campaign_id", 0),
        status=args.get("status", "matched"),
        deliverables=args.get("deliverables", []),
        cost=args.get("cost", 0.0),
    )
    return json.dumps({"success": True, "influencer_campaign": result})


def _list_influencer_campaigns(args: dict) -> str:
    db = _get_db()
    result = db.list_influencer_campaigns(
        campaign_id=args.get("campaign_id"),
        influencer_id=args.get("influencer_id"),
        limit=args.get("limit", 50),
    )
    return json.dumps({"success": True, "influencer_campaigns": result, "count": len(result)})


def _update_influencer_campaign(args: dict) -> str:
    db = _get_db()
    ic_id = args.get("id", 0)
    updates = {}
    for key in ("status", "outreach_sent", "outreach_opened", "response_received",
                 "cost", "deliverables", "content_ids"):
        if key in args:
            updates[key] = args[key]
    result = db.update_influencer_campaign(ic_id, **updates)
    return json.dumps({"success": True, "influencer_campaign": result})


# --- Asset handlers ---

def _create_asset(args: dict) -> str:
    db = _get_db()
    result = db.create_asset(
        name=args.get("name", "Untitled Asset"),
        asset_type=args.get("asset_type", "image"),
        file_path=args.get("file_path", ""),
        url=args.get("url", ""),
        prompt=args.get("prompt", ""),
        model=args.get("model", ""),
        width=args.get("width", 0),
        height=args.get("height", 0),
        duration_secs=args.get("duration_secs", 0.0),
        format=args.get("format", ""),
        campaign_id=args.get("campaign_id"),
        content_id=args.get("content_id"),
        brief=args.get("brief", ""),
        variations=args.get("variations", []),
        status=args.get("status", "draft"),
        tags=args.get("tags", []),
    )
    return json.dumps({"success": True, "asset": result})


def _list_assets(args: dict) -> str:
    db = _get_db()
    result = db.list_assets(
        asset_type=args.get("asset_type"),
        campaign_id=args.get("campaign_id"),
        status=args.get("status"),
        limit=args.get("limit", 50),
    )
    return json.dumps({"success": True, "assets": result, "count": len(result)})


def _get_asset(args: dict) -> str:
    db = _get_db()
    result = db.get_asset(args.get("asset_id", 0))
    if result is None:
        return json.dumps({"error": "Asset not found"})
    return json.dumps({"success": True, "asset": result})


def _update_asset(args: dict) -> str:
    db = _get_db()
    asset_id = args.get("asset_id", 0)
    updates = {}
    for key in ("name", "asset_type", "file_path", "url", "prompt", "model",
                 "width", "height", "duration_secs", "format",
                 "campaign_id", "content_id", "brief", "variations",
                 "status", "tags"):
        if key in args:
            updates[key] = args[key]
    result = db.update_asset(asset_id, **updates)
    return json.dumps({"success": True, "asset": result})


# --- Engagement handlers ---

def _record_engagement(args: dict) -> str:
    db = _get_db()
    result = db.record_engagement(
        content_id=args.get("content_id", 0),
        platform=args.get("platform", ""),
        impressions=args.get("impressions", 0),
        reach=args.get("reach", 0),
        likes=args.get("likes", 0),
        comments=args.get("comments", 0),
        shares=args.get("shares", 0),
        saves=args.get("saves", 0),
        clicks=args.get("clicks", 0),
        video_views=args.get("video_views", 0),
        watch_time_secs=args.get("watch_time_secs", 0.0),
        engagement_rate=args.get("engagement_rate", 0.0),
        sentiment=args.get("sentiment", "neutral"),
    )
    return json.dumps({"success": True, "engagement": result})


def _get_engagements(args: dict) -> str:
    db = _get_db()
    result = db.get_engagements(
        content_id=args.get("content_id"),
        platform=args.get("platform"),
        limit=args.get("limit", 50),
    )
    return json.dumps({"success": True, "engagements": result, "count": len(result)})


# --- Conversion handlers ---

def _record_conversion(args: dict) -> str:
    db = _get_db()
    result = db.record_conversion(
        content_id=args.get("content_id"),
        campaign_id=args.get("campaign_id"),
        influencer_id=args.get("influencer_id"),
        conversion_type=args.get("conversion_type", "lead"),
        value=args.get("value", 0.0),
        revenue=args.get("revenue", 0.0),
        source=args.get("source", ""),
        attribution_model=args.get("attribution_model", "last_touch"),
        tracking_id=args.get("tracking_id", ""),
    )
    return json.dumps({"success": True, "conversion": result})


def _get_conversions(args: dict) -> str:
    db = _get_db()
    result = db.get_conversions(
        campaign_id=args.get("campaign_id"),
        content_id=args.get("content_id"),
        influencer_id=args.get("influencer_id"),
        limit=args.get("limit", 100),
    )
    return json.dumps({"success": True, "conversions": result, "count": len(result)})


# --- Schedule handlers ---

def _create_schedule(args: dict) -> str:
    db = _get_db()
    result = db.create_schedule(
        content_id=args.get("content_id", 0),
        platform=args.get("platform", ""),
        scheduled_at=args.get("scheduled_at", 0),
        status=args.get("status", "pending"),
    )
    return json.dumps({"success": True, "schedule": result})


def _get_schedules(args: dict) -> str:
    db = _get_db()
    result = db.get_schedules(
        content_id=args.get("content_id"),
        status=args.get("status"),
        limit=args.get("limit", 50),
    )
    return json.dumps({"success": True, "schedules": result, "count": len(result)})


def _update_schedule(args: dict) -> str:
    db = _get_db()
    schedule_id = args.get("schedule_id", 0)
    updates = {}
    for key in ("published_at", "status", "publish_url", "error", "retry_count"):
        if key in args:
            updates[key] = args[key]
    result = db.update_schedule(schedule_id, **updates)
    return json.dumps({"success": True, "schedule": result})


# --- Video Pipeline handlers ---

def _create_video(args: dict) -> str:
    db = _get_db()
    result = db.create_video(
        title=args.get("title", "Untitled Video"),
        brief=args.get("brief", ""),
        script=args.get("script", ""),
        storyboard=args.get("storyboard", {}),
        assets=args.get("assets", []),
        campaign_id=args.get("campaign_id"),
        content_id=args.get("content_id"),
        status=args.get("status", "brief"),
        duration_secs=args.get("duration_secs", 0.0),
        resolution=args.get("resolution", ""),
    )
    return json.dumps({"success": True, "video": result})


def _list_videos(args: dict) -> str:
    db = _get_db()
    result = db.list_videos(
        status=args.get("status"),
        campaign_id=args.get("campaign_id"),
        limit=args.get("limit", 50),
    )
    return json.dumps({"success": True, "videos": result, "count": len(result)})


def _get_video(args: dict) -> str:
    db = _get_db()
    result = db.get_video(args.get("video_id", 0))
    if result is None:
        return json.dumps({"error": "Video not found"})
    return json.dumps({"success": True, "video": result})


def _update_video(args: dict) -> str:
    db = _get_db()
    video_id = args.get("video_id", 0)
    updates = {}
    for key in ("title", "brief", "script", "storyboard", "assets",
                 "video_path", "export_path", "variations",
                 "campaign_id", "content_id", "status", "duration_secs", "resolution"):
        if key in args:
            updates[key] = args[key]
    result = db.update_video(video_id, **updates)
    return json.dumps({"success": True, "video": result})


# --- Attribution handlers ---

def _record_attribution(args: dict) -> str:
    db = _get_db()
    result = db.record_attribution(
        campaign_id=args.get("campaign_id"),
        content_id=args.get("content_id"),
        influencer_id=args.get("influencer_id"),
        channel=args.get("channel", ""),
        impressions=args.get("impressions", 0),
        clicks=args.get("clicks", 0),
        leads=args.get("leads", 0),
        conversions=args.get("conversions", 0),
        revenue=args.get("revenue", 0.0),
        cost=args.get("cost", 0.0),
        model=args.get("model", "last_touch"),
        period_start=args.get("period_start", ""),
        period_end=args.get("period_end", ""),
    )
    return json.dumps({"success": True, "attribution": result})


def _get_attribution(args: dict) -> str:
    db = _get_db()
    result = db.get_attribution(
        campaign_id=args.get("campaign_id"),
        content_id=args.get("content_id"),
        influencer_id=args.get("influencer_id"),
        limit=args.get("limit", 100),
    )
    return json.dumps({"success": True, "attribution": result, "count": len(result)})


# --- Analytics handlers ---

def _top_content(args: dict) -> str:
    db = _get_db()
    result = db.get_top_content(
        limit=args.get("limit", 10),
        platform=args.get("platform"),
    )
    return json.dumps({"success": True, "top_content": result, "count": len(result)})


# --- Schema ---

MEDIA_FARM_SCHEMA = {
    "name": "media_farm",
    "description": (
        "Guardian Media Farm tracking system. Manages content, campaigns, "
        "influencers, assets, engagements, conversions, schedules, video "
        "pipelines, and ROI attribution across social, influencer, photo/"
        "creative, and video/media farms. Always returns JSON."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "The action to perform.",
                "enum": [
                    "create_campaign", "list_campaigns", "get_campaign",
                    "update_campaign", "campaign_summary",
                    "create_content", "list_content", "get_content",
                    "update_content", "delete_content", "content_performance",
                    "create_influencer", "list_influencers", "get_influencer",
                    "update_influencer", "influencer_roi",
                    "create_influencer_campaign", "list_influencer_campaigns",
                    "update_influencer_campaign",
                    "create_asset", "list_assets", "get_asset", "update_asset",
                    "record_engagement", "get_engagements",
                    "record_conversion", "get_conversions",
                    "create_schedule", "get_schedules", "update_schedule",
                    "create_video", "list_videos", "get_video", "update_video",
                    "record_attribution", "get_attribution", "top_content",
                ],
            },
            "name": {"type": "string", "description": "Name for campaigns, content, assets, or videos."},
            "title": {"type": "string", "description": "Title for content or video."},
            "handle": {"type": "string", "description": "Influencer handle/username."},
            "campaign_id": {"type": "integer", "description": "Campaign ID reference."},
            "content_id": {"type": "integer", "description": "Content ID reference."},
            "influencer_id": {"type": "integer", "description": "Influencer ID reference."},
            "asset_id": {"type": "integer", "description": "Asset ID reference."},
            "video_id": {"type": "integer", "description": "Video pipeline ID reference."},
            "schedule_id": {"type": "integer", "description": "Schedule ID reference."},
            "id": {"type": "integer", "description": "Influencer campaign ID."},
            "campaign_type": {"type": "string", "description": "Campaign type: social, influencer, photo, video, mixed."},
            "content_type": {"type": "string", "description": "Content type: post, reel, story, thread, video, ad."},
            "platform": {"type": "string", "description": "Platform: x, instagram, tiktok, youtube, linkedin, etc."},
            "platforms": {"type": "array", "items": {"type": "string"}, "description": "List of platforms."},
            "status": {"type": "string", "description": "Status for the entity being operated on."},
            "objective": {"type": "string", "description": "Campaign objective."},
            "audience": {"type": "string", "description": "Target audience description."},
            "start_date": {"type": "string", "description": "Campaign start date (ISO 8601)."},
            "end_date": {"type": "string", "description": "Campaign end date (ISO 8601)."},
            "cadence": {"type": "string", "description": "Posting cadence (e.g., daily, 3x/week)."},
            "voice": {"type": "string", "description": "Brand voice description."},
            "budget": {"type": "number", "description": "Campaign budget."},
            "hook": {"type": "string", "description": "Content hook/first line."},
            "script": {"type": "string", "description": "Content script or full text."},
            "body": {"type": "string", "description": "Content body text."},
            "media_urls": {"type": "array", "items": {"type": "string"}, "description": "Media attachment URLs."},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "Content/asset tags."},
            "scheduled_at": {"type": "integer", "description": "Scheduled publish timestamp (epoch)."},
            "published_at": {"type": "integer", "description": "Actual publish timestamp (epoch)."},
            "platform_post_id": {"type": "string", "description": "Platform-specific post ID after publishing."},
            "followers": {"type": "integer", "description": "Influencer follower count."},
            "engagement_rate": {"type": "number", "description": "Engagement rate (0-100)."},
            "niche": {"type": "string", "description": "Influencer niche/category."},
            "relevance_score": {"type": "number", "description": "Relevance score (0-100)."},
            "audience_demo": {"type": "object", "description": "Audience demographics JSON."},
            "contact_info": {"type": "object", "description": "Contact info JSON."},
            "notes": {"type": "string", "description": "Freeform notes."},
            "min_score": {"type": "number", "description": "Minimum relevance score filter."},
            "cost": {"type": "number", "description": "Cost for influencer campaigns or attribution."},
            "revenue": {"type": "number", "description": "Revenue for conversions or attribution."},
            "value": {"type": "number", "description": "Value for conversions."},
            "conversion_type": {"type": "string", "description": "Type: lead, sale, signup, click, etc."},
            "source": {"type": "string", "description": "Conversion source/tracking origin."},
            "attribution_model": {"type": "string", "description": "Attribution model: last_touch, first_touch, linear, etc."},
            "tracking_id": {"type": "string", "description": "External tracking ID."},
            "impressions": {"type": "integer", "description": "Impression count."},
            "reach": {"type": "integer", "description": "Reach count."},
            "likes": {"type": "integer", "description": "Like count."},
            "comments": {"type": "integer", "description": "Comment count."},
            "shares": {"type": "integer", "description": "Share count."},
            "saves": {"type": "integer", "description": "Save count."},
            "clicks": {"type": "integer", "description": "Click count."},
            "video_views": {"type": "integer", "description": "Video view count."},
            "watch_time_secs": {"type": "number", "description": "Total watch time in seconds."},
            "sentiment": {"type": "string", "description": "Sentiment: positive, neutral, negative."},
            "leads": {"type": "integer", "description": "Lead count for attribution."},
            "conversions": {"type": "integer", "description": "Conversion count for attribution."},
            "channel": {"type": "string", "description": "Attribution channel."},
            "period_start": {"type": "string", "description": "Attribution period start (ISO 8601)."},
            "period_end": {"type": "string", "description": "Attribution period end (ISO 8601)."},
            "model": {"type": "string", "description": "Attribution or video model name."},
            "asset_type": {"type": "string", "description": "Asset type: image, video, thumbnail, ad_creative, graphic."},
            "file_path": {"type": "string", "description": "Local file path for assets."},
            "url": {"type": "string", "description": "Remote URL for assets."},
            "prompt": {"type": "string", "description": "Generation prompt for assets."},
            "width": {"type": "integer", "description": "Image/video width in pixels."},
            "height": {"type": "integer", "description": "Image/video height in pixels."},
            "duration_secs": {"type": "number", "description": "Duration in seconds for video assets."},
            "format": {"type": "string", "description": "File format (png, jpg, mp4, etc.)."},
            "file_size": {"type": "integer", "description": "File size in bytes."},
            "brief": {"type": "string", "description": "Creative brief for assets or videos."},
            "variations": {"type": "array", "description": "List of variation objects."},
            "publish_url": {"type": "string", "description": "URL after publishing."},
            "error": {"type": "string", "description": "Error message for failed schedules."},
            "retry_count": {"type": "integer", "description": "Number of publish retries."},
            "storyboard": {"type": "object", "description": "Video storyboard JSON."},
            "assets": {"type": "array", "description": "List of asset references."},
            "video_path": {"type": "string", "description": "Path to rendered video."},
            "export_path": {"type": "string", "description": "Path to exported video."},
            "resolution": {"type": "string", "description": "Video resolution (e.g., 1920x1080)."},
            "outreach_sent": {"type": "integer", "description": "Timestamp of outreach sent."},
            "outreach_opened": {"type": "integer", "description": "Timestamp of outreach opened."},
            "response_received": {"type": "integer", "description": "Timestamp of response received."},
            "deliverables": {"type": "array", "description": "List of deliverable specifications."},
            "content_ids": {"type": "array", "items": {"type": "integer"}, "description": "Related content IDs."},
            "limit": {"type": "integer", "description": "Max results to return."},
        },
        "required": ["action"],
    },
}

registry.register(
    name="media_farm",
    toolset="media_farm",
    schema=MEDIA_FARM_SCHEMA,
    handler=_handle_media_farm,
    requires_env=[],
    is_async=False,
    emoji="📊",
)
