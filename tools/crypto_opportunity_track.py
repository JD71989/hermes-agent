"""Crypto opportunity tracking tool for the Crypto Intelligence Department.

Tracks opportunity status, deadlines, history, and provides
notification-ready deadline alerts.
"""

import json
import logging
from typing import Any, Dict

from tools.registry import registry, tool_error

logger = logging.getLogger(__name__)


CRYPTO_TRACK_SCHEMA = {
    "name": "crypto_opportunity_track",
    "description": (
        "Track crypto opportunity status, deadlines, and history. "
        "Update status, mark deadlines approaching, get summary "
        "of all tracked opportunities, and query deadline alerts."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "status", "list", "summary", "update_status",
                    "expiring", "history", "delete",
                ],
                "description": "Action to perform.",
            },
            "opportunity_id": {
                "type": "string",
                "description": "Opportunity ID (required for update_status, history, delete).",
            },
            "new_status": {
                "type": "string",
                "enum": [
                    "discovered", "eligible", "in_progress", "submitted",
                    "claimed", "expired", "ineligible", "completed",
                    "failed", "skipped",
                ],
                "description": "New status for update_status action.",
            },
            "filter_status": {
                "type": "string",
                "description": "Filter by status for list action.",
            },
            "filter_type": {
                "type": "string",
                "description": "Filter by opportunity type for list action.",
            },
            "deadline_hours": {
                "type": "integer",
                "description": "Hours ahead to check for expiring (default: 24).",
                "default": 24,
            },
            "notes": {
                "type": "string",
                "description": "Notes to attach to status change.",
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


def _handle_crypto_opportunity_track(
    args: Dict[str, Any], **kwargs: Any
) -> str:
    """Handler for crypto_opportunity_track tool."""
    from agent.crypto_department.opportunity_models import (
        OpportunityStatus,
        OpportunityType,
    )
    from agent.crypto_department.opportunity_store import OpportunityStore

    action = args.get("action")
    store = OpportunityStore()

    if action == "summary":
        return json.dumps(store.summary(), ensure_ascii=False)

    if action == "status":
        opp_id = args.get("opportunity_id")
        if not opp_id:
            return tool_error("opportunity_id required for status action")
        opp = store.get(opp_id)
        if not opp:
            return tool_error(f"Opportunity {opp_id} not found")
        return json.dumps(opp.to_dict(), ensure_ascii=False)

    if action == "list":
        status = None
        if args.get("filter_status"):
            status = OpportunityStatus(args["filter_status"])
        opp_type = None
        if args.get("filter_type"):
            opp_type = OpportunityType(args["filter_type"])
        limit = args.get("limit", 20)
        opps = store.list_all(status=status, opp_type=opp_type, limit=limit)
        return json.dumps({
            "count": len(opps),
            "opportunities": [o.to_dict() for o in opps],
        }, ensure_ascii=False)

    if action == "update_status":
        opp_id = args.get("opportunity_id")
        new_status_str = args.get("new_status")
        if not opp_id or not new_status_str:
            return tool_error("opportunity_id and new_status required")
        new_status = OpportunityStatus(new_status_str)
        notes = args.get("notes", "")
        ok = store.update_status(opp_id, new_status, notes)
        if not ok:
            return tool_error(f"Opportunity {opp_id} not found")
        opp = store.get(opp_id)
        return json.dumps({
            "updated": True,
            "opportunity": opp.to_dict() if opp else None,
        }, ensure_ascii=False)

    if action == "expiring":
        hours = args.get("deadline_hours", 24)
        opps = store.get_expiring(hours=hours)
        return json.dumps({
            "count": len(opps),
            "expiring": [o.to_dict() for o in opps],
        }, ensure_ascii=False)

    if action == "history":
        opp_id = args.get("opportunity_id")
        if not opp_id:
            return tool_error("opportunity_id required for history action")
        history = store.get_history(opp_id)
        return json.dumps({
            "opportunity_id": opp_id,
            "history": history,
        }, ensure_ascii=False)

    if action == "delete":
        opp_id = args.get("opportunity_id")
        if not opp_id:
            return tool_error("opportunity_id required for delete action")
        ok = store.delete(opp_id)
        return json.dumps({"deleted": ok, "id": opp_id}, ensure_ascii=False)

    return tool_error(f"Unknown action: {action}")


registry.register(
    name="crypto_opportunity_track",
    toolset="crypto_intel",
    schema=CRYPTO_TRACK_SCHEMA,
    handler=_handle_crypto_opportunity_track,
    emoji="📋",
)
