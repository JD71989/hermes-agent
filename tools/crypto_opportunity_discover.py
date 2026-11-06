"""Crypto opportunity discovery tool for the Crypto Intelligence Department.

Discovers airdrops, quests, faucets, campaigns, grants, and ecosystem
incentive opportunities. Uses structured data from public sources.

The tool is read-only — it discovers and scores opportunities but
does NOT automate participation.
"""

import json
import logging
from typing import Any, Dict, List

from tools.registry import registry, tool_error

logger = logging.getLogger(__name__)


CRYPTO_DISCOVER_SCHEMA = {
    "name": "crypto_opportunity_discover",
    "description": (
        "Discover crypto opportunities: airdrops, quests, faucets, "
        "campaigns, grants, ecosystem incentives, liquidity mining, "
        "testnets, and more. Returns structured opportunity data with "
        "initial scoring (expected value, fees, time cost, risk, confidence). "
        "Read-only — does not automate participation."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "opportunity_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Filter by types: airdrop, quest, faucet, reward, "
                    "campaign, grant, ecosystem_incentive, liquidity_mining, "
                    "staking_reward, testnet, referral, trading_competition. "
                    "Omit for all types."
                ),
            },
            "chains": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filter by chain names (e.g. ethereum, solana, base).",
            },
            "projects": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filter by project names.",
            },
            "min_expected_value_usd": {
                "type": "number",
                "description": "Minimum expected reward value in USD (default: 0).",
                "default": 0,
            },
            "max_risk_score": {
                "type": "number",
                "description": "Maximum risk score 0-1 (default: 0.8).",
                "default": 0.8,
            },
            "limit": {
                "type": "integer",
                "description": "Maximum results to return (default: 20).",
                "default": 20,
            },
        },
        "required": [],
    },
}


def _generate_default_opportunities() -> List[Dict[str, Any]]:
    """Generate structured default opportunity templates.

    In production this would query external APIs. These templates
    provide the agent with actionable categories to investigate.
    """
    templates = [
        {
            "type": "airdrop",
            "name": "Check Unclaimed Airdrops",
            "description": (
                "Check known wallets for unclaimed airdrops from recent "
                "protocol launches (LayerZero, Wormhole, EigenLayer, zkSync, "
                "Layer3, etc.). Use web_search to find current claim portals."
            ),
            "project": "Various",
            "chain": "multi",
            "required_actions": [
                "Search 'unclaimed airdrops 2026' for current claim portals",
                "Check wallet addresses against known claim sites",
                "Verify claim deadlines",
            ],
            "eligibility": ["Must have interacted with qualifying protocols"],
            "estimated_reward": "$10-500+ depending on protocol and activity",
            "time_cost_hours": 2.0,
            "risk_score": 0.2,
            "confidence": 0.6,
            "tags": ["airdrop", "claims"],
        },
        {
            "type": "quest",
            "name": "Layer3 / Galxe / Zealy Quest Platforms",
            "description": (
                "Quest platforms offer on-chain and social tasks for rewards. "
                "Common patterns: bridge tokens, swap on DEX, provide liquidity, "
                "complete social tasks. Use browser_navigate to check active campaigns."
            ),
            "project": "Layer3/Galxe/Zealy",
            "chain": "multi",
            "required_actions": [
                "Visit layer3.xyz, galxe.com, or zealy.io",
                "Find active campaigns with token rewards",
                "Complete quest requirements",
            ],
            "eligibility": ["Crypto wallet", "Social media accounts"],
            "estimated_reward": "$5-50 per quest",
            "time_cost_hours": 1.0,
            "risk_score": 0.15,
            "confidence": 0.7,
            "tags": ["quest", "tasks"],
        },
        {
            "type": "faucet",
            "name": "Testnet Faucets",
            "description": (
                "Request free testnet tokens for development/testing. "
                "Some testnets reward participants who help test the network "
                "ahead of mainnet launch (potential future airdrop)."
            ),
            "project": "Various",
            "chain": "testnet",
            "required_actions": [
                "Search for active testnet faucets",
                "Request testnet tokens",
                "Complete testnet activities",
            ],
            "eligibility": ["GitHub account or social verification"],
            "estimated_reward": "$0 (potential future airdrop value)",
            "time_cost_hours": 0.5,
            "risk_score": 0.05,
            "confidence": 0.5,
            "tags": ["faucet", "testnet"],
        },
        {
            "type": "ecosystem_incentive",
            "name": "Ecosystem Grant Programs",
            "description": (
                "Many ecosystems (Solana Foundation, Arbitrum, Base, Optimism, "
                "Polygon) run grant programs for builders. Apply with a project "
                "idea or contribute to existing open-source projects."
            ),
            "project": "Various",
            "chain": "multi",
            "required_actions": [
                "Research active grant programs per ecosystem",
                "Prepare project proposal or contribution plan",
                "Submit application",
            ],
            "eligibility": ["Active development project", "Technical capability"],
            "estimated_reward": "$1,000-100,000+ depending on scope",
            "time_cost_hours": 10.0,
            "risk_score": 0.3,
            "confidence": 0.4,
            "tags": ["grant", "builder"],
        },
        {
            "type": "liquidity_mining",
            "name": "DEX Liquidity Mining Programs",
            "description": (
                "Provide liquidity to DEX pools that offer token incentives. "
                "Calculate APY from trading fees + token rewards. Be aware "
                "of impermanent loss risk."
            ),
            "project": "Various DEXes",
            "chain": "multi",
            "required_actions": [
                "Use crypto_opportunity_score with yields data from DeFiLlama",
                "Evaluate APY vs impermanent loss risk",
                "Provide liquidity to selected pools",
            ],
            "eligibility": ["LP tokens or assets to deposit"],
            "estimated_reward": "Varies by APY and deposit size",
            "time_cost_hours": 2.0,
            "risk_score": 0.45,
            "confidence": 0.6,
            "tags": ["defi", "liquidity", "yield"],
        },
    ]
    return templates


def _handle_crypto_opportunity_discover(
    args: Dict[str, Any], **kwargs: Any
) -> str:
    """Handler for crypto_opportunity_discover tool."""
    from agent.crypto_department.opportunity_models import (
        Opportunity,
        OpportunitySource,
        OpportunityStatus,
        OpportunityType,
        ScoringDimensions,
    )
    from agent.crypto_department.opportunity_scorer import rank_opportunities
    from agent.crypto_department.opportunity_store import OpportunityStore

    opp_type_filter = [t.lower() for t in args.get("opportunity_types", [])]
    chain_filter = [c.lower() for c in args.get("chains", [])]
    project_filter = [p.lower() for p in args.get("projects", [])]
    min_ev = args.get("min_expected_value_usd", 0)
    max_risk = args.get("max_risk_score", 0.8)
    limit = min(args.get("limit", 20), 50)

    templates = _generate_default_opportunities()
    opportunities = []

    for tmpl in templates:
        if opp_type_filter and tmpl["type"] not in opp_type_filter:
            continue
        if chain_filter and tmpl["chain"].lower() not in chain_filter and tmpl["chain"] != "multi":
            continue
        if project_filter and tmpl["project"].lower() not in [p.lower() for p in project_filter]:
            continue

        scoring = ScoringDimensions(
            expected_reward_usd=0.0,
            time_cost_hours=tmpl.get("time_cost_hours", 1.0),
            risk_score=tmpl.get("risk_score", 0.5),
            confidence=tmpl.get("confidence", 0.5),
        )

        opp = Opportunity(
            type=OpportunityType(tmpl["type"]),
            name=tmpl["name"],
            description=tmpl["description"],
            project=tmpl.get("project", ""),
            chain=tmpl.get("chain", ""),
            status=OpportunityStatus.DISCOVERED,
            source=OpportunitySource(name="guardian_crypto_intel", url=""),
            scoring=scoring,
            required_actions=tmpl.get("required_actions", []),
            eligibility=tmpl.get("eligibility", []),
            estimated_reward=tmpl.get("estimated_reward", ""),
            tags=tmpl.get("tags", []),
        )
        opportunities.append(opp)

    ranked = rank_opportunities(opportunities)
    ranked = [o for o in ranked if o.scoring.risk_score <= max_risk]
    ranked = ranked[:limit]

    store = OpportunityStore()
    for opp in ranked:
        store.upsert(opp)

    return json.dumps({
        "discovered": len(ranked),
        "opportunities": [o.to_dict() for o in ranked],
        "summary": store.summary(),
    }, ensure_ascii=False)


registry.register(
    name="crypto_opportunity_discover",
    toolset="crypto_intel",
    schema=CRYPTO_DISCOVER_SCHEMA,
    handler=_handle_crypto_opportunity_discover,
    emoji="🔍",
)
