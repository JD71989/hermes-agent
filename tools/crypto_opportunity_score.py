"""Crypto opportunity scoring tool for the Crypto Intelligence Department.

Scores and ranks opportunities using:
  EXPECTED VALUE - FEES - TIME COST - RISK

Tracks: source, eligibility, deadline, required actions, estimated reward,
confidence, risk, status, evidence.
"""

import json
import logging
from typing import Any, Dict, Optional

from tools.registry import registry, tool_error

logger = logging.getLogger(__name__)


CRYPTO_SCORE_SCHEMA = {
    "name": "crypto_opportunity_score",
    "description": (
        "Score a crypto opportunity using: EXPECTED VALUE minus FEES minus "
        "TIME COST minus RISK. Returns full cost breakdown, composite score, "
        "ranking recommendation, and stores the result. Tracks: source, "
        "eligibility, deadline, required actions, estimated reward, "
        "confidence, risk, status, evidence."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "opportunity_id": {
                "type": "string",
                "description": "ID of an existing opportunity to re-score.",
            },
            "expected_reward_usd": {
                "type": "number",
                "description": "Estimated reward value in USD.",
            },
            "fees_usd": {
                "type": "number",
                "description": "Total fees (gas, platform, exchange) in USD.",
                "default": 0,
            },
            "time_cost_hours": {
                "type": "number",
                "description": "Estimated time to complete in hours.",
                "default": 1.0,
            },
            "risk_score": {
                "type": "number",
                "description": "Risk score 0-1 (0=no risk, 1=very high risk).",
                "default": 0.5,
            },
            "confidence": {
                "type": "number",
                "description": "Confidence in estimates 0-1.",
                "default": 0.5,
            },
            "upfront_cost_usd": {
                "type": "number",
                "description": "Upfront capital required in USD.",
                "default": 0,
            },
            "gas_cost_usd": {
                "type": "number",
                "description": "Estimated gas cost in USD.",
                "default": 0,
            },
            "automation_permit": {
                "type": "string",
                "enum": ["none", "read_only", "partial", "full"],
                "description": "Level of automation permitted by the service.",
                "default": "none",
            },
            "deadline": {
                "type": "string",
                "description": "ISO datetime deadline for the opportunity.",
            },
            "source_url": {
                "type": "string",
                "description": "Source URL for the opportunity.",
            },
            "evidence": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Evidence supporting the opportunity claims.",
            },
            "hourly_wage": {
                "type": "number",
                "description": "Override hourly cost rate (default: $25/h).",
            },
        },
        "required": [],
    },
}


def _handle_crypto_opportunity_score(
    args: Dict[str, Any], **kwargs: Any
) -> str:
    """Handler for crypto_opportunity_score tool."""
    from agent.crypto_department.opportunity_models import (
        AutomationPermitted,
        Opportunity,
        OpportunitySource,
        ScoringDimensions,
    )
    from agent.crypto_department.opportunity_scorer import rank_opportunities, score_opportunity
    from agent.crypto_department.opportunity_store import OpportunityStore

    store = OpportunityStore()
    opp_id = args.get("opportunity_id")

    if opp_id:
        opp = store.get(opp_id)
        if not opp:
            return tool_error(f"Opportunity {opp_id} not found")
        for key, val in args.items():
            if key == "opportunity_id":
                continue
            if key == "expected_reward_usd" and val is not None:
                opp.scoring.expected_reward_usd = val
            elif key == "fees_usd" and val is not None:
                opp.scoring.fees_usd = val
            elif key == "time_cost_hours" and val is not None:
                opp.scoring.time_cost_hours = val
            elif key == "risk_score" and val is not None:
                opp.scoring.risk_score = max(0.0, min(1.0, val))
            elif key == "confidence" and val is not None:
                opp.scoring.confidence = max(0.0, min(1.0, val))
            elif key == "upfront_cost_usd" and val is not None:
                opp.scoring.upfront_cost_usd = val
            elif key == "gas_cost_usd" and val is not None:
                opp.scoring.gas_cost_usd = val
            elif key == "automation_permit" and val is not None:
                opp.scoring.automation_permit = AutomationPermitted(val)
            elif key == "deadline" and val is not None:
                opp.deadline = val
            elif key == "source_url" and val is not None:
                opp.source = OpportunitySource(
                    name=opp.source.name or "user", url=val,
                    reliability=opp.source.reliability,
                )
            elif key == "evidence" and val is not None:
                opp.evidence = val
        hourly_wage = args.get("hourly_wage")
        opp.result = score_opportunity(opp.scoring, hourly_wage=hourly_wage)
        store.upsert(opp)
        return json.dumps(opp.to_dict(), ensure_ascii=False)

    scoring = ScoringDimensions(
        expected_reward_usd=args.get("expected_reward_usd", 0),
        fees_usd=args.get("fees_usd", 0),
        time_cost_hours=args.get("time_cost_hours", 1.0),
        risk_score=max(0.0, min(1.0, args.get("risk_score", 0.5))),
        confidence=max(0.0, min(1.0, args.get("confidence", 0.5))),
        upfront_cost_usd=args.get("upfront_cost_usd", 0),
        gas_cost_usd=args.get("gas_cost_usd", 0),
        automation_permit=AutomationPermitted(args.get("automation_permit", "none")),
    )

    result = score_opportunity(
        scoring, hourly_wage=args.get("hourly_wage")
    )

    return json.dumps({
        "scoring": scoring.to_dict(),
        "result": result.to_dict(),
    }, ensure_ascii=False)


registry.register(
    name="crypto_opportunity_score",
    toolset="crypto_intel",
    schema=CRYPTO_SCORE_SCHEMA,
    handler=_handle_crypto_opportunity_score,
    emoji="📊",
)
