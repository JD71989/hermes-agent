"""Crypto event tracking tool for the Crypto Intelligence Department.

Tracks crypto events, deadlines, token unlocks, protocol launches,
and provides notification-ready deadline alerts.
"""

import json
import logging
from typing import Any, Dict

from tools.registry import registry, tool_error

logger = logging.getLogger(__name__)


CRYPTO_EVENT_TRACK_SCHEMA = {
    "name": "crypto_event_track",
    "description": (
        "Track crypto events: token unlocks, protocol launches, "
        "governance votes, airdrop deadlines, testnet phases, "
        "upgrade dates, and more. Add events, list events, "
        "check expiring events, and get summaries."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "list", "expiring", "summary", "delete"],
                "description": "Action to perform.",
            },
            "title": {
                "type": "string",
                "description": "Event title (required for add).",
            },
            "event_type": {
                "type": "string",
                "description": (
                    "Event type: token_unlock, protocol_launch, governance_vote, "
                    "airdrop_deadline, testnet_phase, upgrade, conference, "
                    "listing, other."
                ),
                "default": "other",
            },
            "description": {
                "type": "string",
                "description": "Event description.",
            },
            "project": {
                "type": "string",
                "description": "Project name.",
            },
            "chain": {
                "type": "string",
                "description": "Blockchain chain.",
            },
            "start_time": {
                "type": "string",
                "description": "ISO datetime start time.",
            },
            "end_time": {
                "type": "string",
                "description": "ISO datetime end time / deadline.",
            },
            "importance": {
                "type": "string",
                "enum": ["low", "normal", "high", "critical"],
                "description": "Event importance level.",
                "default": "normal",
            },
            "source_url": {
                "type": "string",
                "description": "Source URL for the event.",
            },
            "notes": {
                "type": "string",
                "description": "Additional notes.",
            },
            "event_id": {
                "type": "string",
                "description": "Event ID (for delete action).",
            },
            "deadline_hours": {
                "type": "integer",
                "description": "Hours ahead for expiring action (default: 24).",
                "default": 24,
            },
            "limit": {
                "type": "integer",
                "description": "Max results for list action (default: 20).",
                "default": 20,
            },
        },
        "required": ["action"],
    },
}


def _handle_crypto_event_track(
    args: Dict[str, Any], **kwargs: Any
) -> str:
    """Handler for crypto_event_track tool."""
    from agent.crypto_department.event_tracker import EventTracker

    action = args.get("action")
    tracker = EventTracker()

    if action == "add":
        title = args.get("title")
        if not title:
            return tool_error("title required for add action")
        event_id = tracker.add_event(
            title=title,
            event_type=args.get("event_type", "other"),
            description=args.get("description", ""),
            project=args.get("project", ""),
            chain=args.get("chain", ""),
            start_time=args.get("start_time"),
            end_time=args.get("end_time"),
            importance=args.get("importance", "normal"),
            source_url=args.get("source_url", ""),
            notes=args.get("notes", ""),
        )
        event = tracker.get_event(event_id)
        return json.dumps({"added": True, "event": event}, ensure_ascii=False)

    if action == "list":
        event_type = args.get("event_type")
        project = args.get("project")
        limit = args.get("limit", 20)
        events = tracker.list_events(
            event_type=event_type, project=project, limit=limit
        )
        return json.dumps({
            "count": len(events),
            "events": events,
        }, ensure_ascii=False)

    if action == "expiring":
        hours = args.get("deadline_hours", 24)
        events = tracker.get_expiring(hours=hours)
        return json.dumps({
            "count": len(events),
            "expiring": events,
        }, ensure_ascii=False)

    if action == "summary":
        return json.dumps(tracker.summary(), ensure_ascii=False)

    if action == "delete":
        event_id = args.get("event_id")
        if not event_id:
            return tool_error("event_id required for delete action")
        ok = tracker.delete_event(event_id)
        return json.dumps({"deleted": ok, "id": event_id}, ensure_ascii=False)

    return tool_error(f"Unknown action: {action}")


registry.register(
    name="crypto_event_track",
    toolset="crypto_event",
    schema=CRYPTO_EVENT_TRACK_SCHEMA,
    handler=_handle_crypto_event_track,
    emoji="📅",
)
