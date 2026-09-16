"""``hermes media`` subcommand parser and handler.

Provides CLI access to the Guardian Media Farm database for managing
content, campaigns, influencers, assets, engagements, conversions,
schedules, video pipelines, and attribution tracking.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any, Callable, Optional


def _init_db() -> Any:
    from tools import media_farm_db as db_mod
    db_mod.init_db()
    return db_mod


def _fmt_ts(ts: Optional[int]) -> str:
    if not ts:
        return ""
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


def _print_table(headers: list[str], rows: list[list[str]], widths: Optional[list[int]] = None) -> None:
    if not rows:
        print("  (no results)")
        return
    if widths is None:
        widths = []
        for i, h in enumerate(headers):
            col_widths = [len(str(row[i])) if i < len(row) else 0 for row in rows]
            widths.append(max(len(h), max(col_widths) if col_widths else 0))
    header_line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    print(header_line)
    print("  ".join("-" * w for w in widths))
    for row in rows:
        line = "  ".join(str(row[i] if i < len(row) else "").ljust(widths[i]) for i in range(len(headers)))
        print(line)


# ---------------------------------------------------------------------------
# Campaign commands
# ---------------------------------------------------------------------------

def _cmd_campaign_list(db: Any, args: argparse.Namespace) -> None:
    campaigns = db.list_campaigns(status=getattr(args, "status", None), limit=getattr(args, "limit", 50))
    if getattr(args, "json_output", False):
        print(json.dumps(campaigns, indent=2))
        return
    headers = ["ID", "Name", "Type", "Status", "Budget", "Created"]
    rows = [[c["id"], c["name"][:40], c["campaign_type"], c["status"],
             f"${c['budget']:.0f}", _fmt_ts(c["created_at"])] for c in campaigns]
    print(f"\nCampaigns ({len(campaigns)}):")
    _print_table(headers, rows)


def _cmd_campaign_create(db: Any, args: argparse.Namespace) -> None:
    platforms = args.platforms.split(",") if args.platforms else []
    result = db.create_campaign(
        name=args.name,
        campaign_type=getattr(args, "type", "social"),
        objective=getattr(args, "objective", ""),
        audience=getattr(args, "audience", ""),
        platforms=platforms,
        budget=getattr(args, "budget", 0.0),
    )
    print(f"Created campaign {result['id']}: {result['name']}")


def _cmd_campaign_show(db: Any, args: argparse.Namespace) -> None:
    campaign = db.get_campaign(args.campaign_id)
    if not campaign:
        print(f"Campaign {args.campaign_id} not found")
        return
    if getattr(args, "json_output", False):
        print(json.dumps(campaign, indent=2))
        return
    summary = db.get_campaign_summary(args.campaign_id)
    print(f"\nCampaign: {campaign['name']} (ID: {campaign['id']})")
    print(f"  Type: {campaign['campaign_type']}")
    print(f"  Status: {campaign['status']}")
    print(f"  Objective: {campaign['objective'] or '(none)'}")
    print(f"  Platforms: {', '.join(campaign['platforms']) or '(none)'}")
    print(f"  Budget: ${campaign['budget']:.2f}")
    print(f"\n  Performance:")
    print(f"    Content: {summary['content_total']} total, {summary['content_published']} published")
    print(f"    Impressions: {summary['impressions']:,}")
    print(f"    Engagement: {summary['likes']:,} likes, {summary['comments']:,} comments, {summary['shares']:,} shares")
    print(f"    Clicks: {summary['clicks']:,}")
    print(f"    Conversions: {summary['conversions']}")
    print(f"    Revenue: ${summary['total_revenue']:,.2f}")
    print(f"    Cost: ${summary['total_cost']:,.2f}")
    print(f"    ROI: {summary['roi_percent']:.1f}%")
    print(f"    Influencers: {summary['influencers']}")


# ---------------------------------------------------------------------------
# Content commands
# ---------------------------------------------------------------------------

def _cmd_content_list(db: Any, args: argparse.Namespace) -> None:
    content = db.list_content(
        status=getattr(args, "status", None),
        platform=getattr(args, "platform", None),
        campaign_id=getattr(args, "campaign_id", None),
        limit=getattr(args, "limit", 50),
    )
    if getattr(args, "json_output", False):
        print(json.dumps(content, indent=2))
        return
    headers = ["ID", "Title", "Type", "Platform", "Status", "Created"]
    rows = [[c["id"], c["title"][:40], c["content_type"], c["platform"], c["status"],
             _fmt_ts(c["created_at"])] for c in content]
    print(f"\nContent ({len(content)}):")
    _print_table(headers, rows)


def _cmd_content_create(db: Any, args: argparse.Namespace) -> None:
    result = db.create_content(
        title=args.title,
        content_type=getattr(args, "type", "post"),
        platform=getattr(args, "platform", ""),
        campaign_id=getattr(args, "campaign_id", None),
    )
    print(f"Created content {result['id']}: {result['title']}")


def _cmd_content_show(db: Any, args: argparse.Namespace) -> None:
    content = db.get_content(args.content_id)
    if not content:
        print(f"Content {args.content_id} not found")
        return
    if getattr(args, "json_output", False):
        print(json.dumps(content, indent=2))
        return
    perf = db.get_content_performance(args.content_id)
    print(f"\nContent: {content['title']} (ID: {content['id']})")
    print(f"  Type: {content['content_type']}")
    print(f"  Platform: {content['platform']}")
    print(f"  Status: {content['status']}")
    print(f"  Campaign: {content['campaign_id'] or '(none)'}")
    if content['hook']:
        print(f"  Hook: {content['hook'][:80]}")
    print(f"\n  Performance:")
    print(f"    Impressions: {perf['impressions']:,}")
    print(f"    Likes: {perf['likes']:,} | Comments: {perf['comments']:,} | Shares: {perf['shares']:,}")
    print(f"    Clicks: {perf['clicks']:,}")
    print(f"    Conversions: {perf['conversions']} | Revenue: ${perf['revenue']:,.2f}")


# ---------------------------------------------------------------------------
# Influencer commands
# ---------------------------------------------------------------------------

def _cmd_influencer_list(db: Any, args: argparse.Namespace) -> None:
    influencers = db.list_influencers(
        status=getattr(args, "status", None),
        platform=getattr(args, "platform", None),
        niche=getattr(args, "niche", None),
        limit=getattr(args, "limit", 50),
    )
    if getattr(args, "json_output", False):
        print(json.dumps(influencers, indent=2))
        return
    headers = ["ID", "Handle", "Platform", "Followers", "Eng%", "Score", "Status"]
    rows = [[i["id"], i["handle"][:30], i["platform"], f"{i['followers']:,}",
             f"{i['engagement_rate']:.1f}", f"{i['relevance_score']:.0f}", i["status"]]
            for i in influencers]
    print(f"\nInfluencers ({len(influencers)}):")
    _print_table(headers, rows)


def _cmd_influencer_create(db: Any, args: argparse.Namespace) -> None:
    result = db.create_influencer(
        handle=args.handle,
        platform=getattr(args, "platform", ""),
        name=getattr(args, "name", ""),
        niche=getattr(args, "niche", ""),
    )
    print(f"Created influencer {result['id']}: {result['handle']}")


def _cmd_influencer_roi(db: Any, args: argparse.Namespace) -> None:
    roi = db.get_influencer_roi(args.influencer_id)
    if getattr(args, "json_output", False):
        print(json.dumps(roi, indent=2))
        return
    print(f"\nInfluencer ROI (ID: {roi['influencer_id']})")
    print(f"  Campaigns: {roi['campaigns_count']}")
    print(f"  Total Cost: ${roi['total_cost']:,.2f}")
    print(f"  Total Revenue: ${roi['total_revenue']:,.2f}")
    print(f"  Conversions: {roi['conversions']}")
    print(f"  ROI: {roi['roi_percent']:.1f}%")


# ---------------------------------------------------------------------------
# Asset commands
# ---------------------------------------------------------------------------

def _cmd_asset_list(db: Any, args: argparse.Namespace) -> None:
    assets = db.list_assets(
        asset_type=getattr(args, "type", None),
        campaign_id=getattr(args, "campaign_id", None),
        status=getattr(args, "status", None),
        limit=getattr(args, "limit", 50),
    )
    if getattr(args, "json_output", False):
        print(json.dumps(assets, indent=2))
        return
    headers = ["ID", "Name", "Type", "Status", "Dims", "Created"]
    rows = [[a["id"], a["name"][:35], a["asset_type"], a["status"],
             f"{a['width']}x{a['height']}" if a['width'] else "",
             _fmt_ts(a["created_at"])] for a in assets]
    print(f"\nAssets ({len(assets)}):")
    _print_table(headers, rows)


# ---------------------------------------------------------------------------
# Video commands
# ---------------------------------------------------------------------------

def _cmd_video_list(db: Any, args: argparse.Namespace) -> None:
    videos = db.list_videos(
        status=getattr(args, "status", None),
        campaign_id=getattr(args, "campaign_id", None),
        limit=getattr(args, "limit", 50),
    )
    if getattr(args, "json_output", False):
        print(json.dumps(videos, indent=2))
        return
    headers = ["ID", "Title", "Status", "Duration", "Resolution", "Created"]
    rows = [[v["id"], v["title"][:35], v["status"],
             f"{v['duration_secs']:.1f}s" if v['duration_secs'] else "",
             v["resolution"] or "", _fmt_ts(v["created_at"])] for v in videos]
    print(f"\nVideos ({len(videos)}):")
    _print_table(headers, rows)


# ---------------------------------------------------------------------------
# Analytics commands
# ---------------------------------------------------------------------------

def _cmd_top_content(db: Any, args: argparse.Namespace) -> None:
    top = db.get_top_content(
        limit=getattr(args, "limit", 10),
        platform=getattr(args, "platform", None),
    )
    if getattr(args, "json_output", False):
        print(json.dumps(top, indent=2))
        return
    headers = ["ID", "Title", "Platform", "Impressions", "Likes", "Shares", "Clicks"]
    rows = [[t["id"], t["title"][:35], t["platform"],
             f"{t['impressions']:,}", f"{t['likes']:,}",
             f"{t['shares']:,}", f"{t['clicks']:,}"] for t in top]
    print(f"\nTop Content ({len(top)}):")
    _print_table(headers, rows)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def media_command(args: argparse.Namespace) -> None:
    db = _init_db()
    command = getattr(args, "media_command", None)
    entity = getattr(args, "media_entity", None)

    if command is None:
        print("Usage: hermes media <entity> <action> [options]")
        print("\nEntities: campaign, content, influencer, asset, video, top")
        print("Run 'hermes media --help' for details.")
        return

    dispatch = {
        ("campaign", "list"): _cmd_campaign_list,
        ("campaign", "create"): _cmd_campaign_create,
        ("campaign", "show"): _cmd_campaign_show,
        ("content", "list"): _cmd_content_list,
        ("content", "create"): _cmd_content_create,
        ("content", "show"): _cmd_content_show,
        ("influencer", "list"): _cmd_influencer_list,
        ("influencer", "create"): _cmd_influencer_create,
        ("influencer", "roi"): _cmd_influencer_roi,
        ("asset", "list"): _cmd_asset_list,
        ("video", "list"): _cmd_video_list,
        ("top", "content"): _cmd_top_content,
    }

    handler = dispatch.get((entity, command))
    if handler:
        handler(db, args)
    else:
        print(f"Unknown command: {entity} {command}")
        print("Valid combinations: campaign/list, campaign/create, campaign/show,")
        print("  content/list, content/create, content/show,")
        print("  influencer/list, influencer/create, influencer/roi,")
        print("  asset/list, video/list, top/content")


def build_media_parser(subparsers: Any, *, cmd_media: Optional[Callable] = None) -> Any:
    """Attach the ``media`` subcommand to ``subparsers``."""
    media_parser = subparsers.add_parser(
        "media", help="Guardian Media Farm management",
        description="Manage content, campaigns, influencers, assets, and video pipelines"
    )
    media_subparsers = media_parser.add_subparsers(dest="media_entity")

    # -- campaign --
    campaign_parser = media_subparsers.add_parser("campaign", help="Campaign management")
    campaign_sub = campaign_parser.add_subparsers(dest="media_command")
    cl = campaign_sub.add_parser("list", help="List campaigns")
    cl.add_argument("--status", help="Filter by status")
    cl.add_argument("--limit", type=int, default=50)
    cl.add_argument("--json", dest="json_output", action="store_true")
    cc = campaign_sub.add_parser("create", help="Create a campaign")
    cc.add_argument("name", help="Campaign name")
    cc.add_argument("--type", default="social", help="Campaign type (default: social)")
    cc.add_argument("--objective", help="Campaign objective")
    cc.add_argument("--audience", help="Target audience")
    cc.add_argument("--platforms", help="Comma-separated platforms")
    cc.add_argument("--budget", type=float, default=0.0, help="Budget")
    cs = campaign_sub.add_parser("show", help="Show campaign details + summary")
    cs.add_argument("campaign_id", type=int)
    cs.add_argument("--json", dest="json_output", action="store_true")

    # -- content --
    content_parser = media_subparsers.add_parser("content", help="Content management")
    content_sub = content_parser.add_subparsers(dest="media_command")
    col = content_sub.add_parser("list", help="List content")
    col.add_argument("--status", help="Filter by status")
    col.add_argument("--platform", help="Filter by platform")
    col.add_argument("--campaign-id", type=int, help="Filter by campaign")
    col.add_argument("--limit", type=int, default=50)
    col.add_argument("--json", dest="json_output", action="store_true")
    coc = content_sub.add_parser("create", help="Create content")
    coc.add_argument("title", help="Content title")
    coc.add_argument("--type", default="post", help="Content type")
    coc.add_argument("--platform", help="Platform")
    coc.add_argument("--campaign-id", type=int, help="Campaign ID")
    cos = content_sub.add_parser("show", help="Show content details + performance")
    cos.add_argument("content_id", type=int)
    cos.add_argument("--json", dest="json_output", action="store_true")

    # -- influencer --
    influencer_parser = media_subparsers.add_parser("influencer", help="Influencer management")
    influencer_sub = influencer_parser.add_subparsers(dest="media_command")
    il = influencer_sub.add_parser("list", help="List influencers")
    il.add_argument("--status", help="Filter by status")
    il.add_argument("--platform", help="Filter by platform")
    il.add_argument("--niche", help="Filter by niche")
    il.add_argument("--limit", type=int, default=50)
    il.add_argument("--json", dest="json_output", action="store_true")
    ic = influencer_sub.add_parser("create", help="Add an influencer")
    ic.add_argument("handle", help="Influencer handle/username")
    ic.add_argument("--platform", help="Platform")
    ic.add_argument("--name", help="Display name")
    ic.add_argument("--niche", help="Niche/category")
    ir = influencer_sub.add_parser("roi", help="Show influencer ROI")
    ir.add_argument("influencer_id", type=int)
    ir.add_argument("--json", dest="json_output", action="store_true")

    # -- asset --
    asset_parser = media_subparsers.add_parser("asset", help="Asset management")
    asset_sub = asset_parser.add_subparsers(dest="media_command")
    al = asset_sub.add_parser("list", help="List assets")
    al.add_argument("--type", dest="asset_type", help="Filter by type")
    al.add_argument("--campaign-id", type=int, help="Filter by campaign")
    al.add_argument("--status", help="Filter by status")
    al.add_argument("--limit", type=int, default=50)
    al.add_argument("--json", dest="json_output", action="store_true")

    # -- video --
    video_parser = media_subparsers.add_parser("video", help="Video pipeline management")
    video_sub = video_parser.add_subparsers(dest="media_command")
    vl = video_sub.add_parser("list", help="List video pipelines")
    vl.add_argument("--status", help="Filter by status")
    vl.add_argument("--campaign-id", type=int, help="Filter by campaign")
    vl.add_argument("--limit", type=int, default=50)
    vl.add_argument("--json", dest="json_output", action="store_true")

    # -- top --
    top_parser = media_subparsers.add_parser("top", help="Analytics")
    top_sub = top_parser.add_subparsers(dest="media_command")
    tc = top_sub.add_parser("content", help="Top performing content")
    tc.add_argument("--limit", type=int, default=10)
    tc.add_argument("--platform", help="Filter by platform")
    tc.add_argument("--json", dest="json_output", action="store_true")

    if cmd_media is not None:
        media_parser.set_defaults(func=cmd_media)

    return media_parser
