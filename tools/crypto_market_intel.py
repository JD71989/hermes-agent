"""Crypto market intelligence tool for the Crypto Intelligence Department.

Gathers market data, DeFi protocol TVL, yield opportunities,
and ecosystem intelligence from public APIs.
"""

import json
import logging
from typing import Any, Dict

from tools.registry import registry, tool_error

logger = logging.getLogger(__name__)


CRYPTO_MARKET_INTEL_SCHEMA = {
    "name": "crypto_market_intel",
    "description": (
        "Gather crypto market intelligence: top coins by market cap, "
        "trending coins, DeFi protocol TVL, yield opportunities, "
        "new protocols, stablecoin overview. Uses CoinGecko and "
        "DeFiLlama public APIs (no API key required)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "enum": [
                    "top_coins", "trending", "coin_detail",
                    "defi_protocols", "new_protocols", "yields",
                    "stablecoins",
                ],
                "description": "Type of market intelligence to gather.",
            },
            "coin_id": {
                "type": "string",
                "description": "CoinGecko coin ID for coin_detail (e.g. 'bitcoin', 'ethereum').",
            },
            "chain": {
                "type": "string",
                "description": "Filter by chain (for yields).",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum results (default: 10).",
                "default": 10,
            },
        },
        "required": ["query"],
    },
}


def _handle_crypto_market_intel(
    args: Dict[str, Any], **kwargs: Any
) -> str:
    """Handler for crypto_market_intel tool."""
    from agent.crypto_department.market_intel import (
        get_coin_detail,
        get_defi_protocols,
        get_new_protocols,
        get_stablecoin_overview,
        get_trending_coins,
        get_top_coins,
        get_yields,
    )

    query = args.get("query")
    limit = args.get("limit", 10)

    if query == "top_coins":
        data = get_top_coins(limit=limit)
        return json.dumps({"query": "top_coins", "count": len(data), "coins": data})

    if query == "trending":
        data = get_trending_coins()
        return json.dumps({"query": "trending", "count": len(data), "coins": data})

    if query == "coin_detail":
        coin_id = args.get("coin_id")
        if not coin_id:
            return tool_error("coin_id required for coin_detail")
        data = get_coin_detail(coin_id)
        return json.dumps({"query": "coin_detail", "coin": data})

    if query == "defi_protocols":
        data = get_defi_protocols(limit=limit)
        return json.dumps({"query": "defi_protocols", "count": len(data), "protocols": data})

    if query == "new_protocols":
        days = args.get("limit", 7)
        data = get_new_protocols(days=days)
        return json.dumps({"query": "new_protocols", "count": len(data), "protocols": data})

    if query == "yields":
        chain = args.get("chain")
        data = get_yields(chain=chain, limit=limit)
        return json.dumps({"query": "yields", "count": len(data), "pools": data})

    if query == "stablecoins":
        data = get_stablecoin_overview()
        return json.dumps({"query": "stablecoins", "count": len(data), "stablecoins": data})

    return tool_error(f"Unknown query: {query}")


registry.register(
    name="crypto_market_intel",
    toolset="crypto_intel",
    schema=CRYPTO_MARKET_INTEL_SCHEMA,
    handler=_handle_crypto_market_intel,
    emoji="💹",
)
