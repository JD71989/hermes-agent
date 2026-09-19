from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
DEFILLAMA_BASE = "https://api.llama.fi"
YIELDS_BASE = "https://yields.llama.fi"
STABLECOINS_BASE = "https://stablecoins.llama.fi"

def _get_json(url: str, params: dict[str, Any] | None = None, timeout: int = 25) -> Any:
    if params:
        url = f"{url}?{urlencode(params)}"
    req = Request(url, headers={"accept": "application/json", "User-Agent": "Guardian-Crypto-Intel/1.0"})
    with urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8")

def _parse_json(payload: str) -> Any:
    import json
    return json.loads(payload)

def _request(url: str, params: dict[str, Any] | None = None) -> Any:
    return _parse_json(_get_json(url, params))

def get_top_coins(limit: int = 10) -> list[dict[str, Any]]:
    n = max(1, min(int(limit), 100))
    data = _request(
        f"{COINGECKO_BASE}/coins/markets",
        {"vs_currency": "usd", "order": "market_cap_desc", "per_page": n, "page": 1, "sparkline": "false"},
    )
    return list(data or [])

def get_trending_coins() -> list[dict[str, Any]]:
    data = _request(f"{COINGECKO_BASE}/search/trending")
    coins = []
    for row in (data or {}).get("coins", []):
        item = row.get("item", row)
        coins.append(item)
    return coins

def get_coin_detail(coin_id: str) -> dict[str, Any]:
    cid = str(coin_id or "").strip()
    if not cid or "/" in cid or "?" in cid or "#" in cid:
        raise ValueError("invalid coin_id")
    return dict(_request(
        f"{COINGECKO_BASE}/coins/{cid}",
        {"localization": "false", "tickers": "false", "market_data": "true", "community_data": "false", "developer_data": "false"},
    ) or {})

def get_defi_protocols(limit: int = 10) -> list[dict[str, Any]]:
    n = max(1, min(int(limit), 100))
    data = list(_request(f"{DEFILLAMA_BASE}/protocols") or [])
    data.sort(key=lambda x: float(x.get("tvl") or 0), reverse=True)
    return data[:n]

def get_new_protocols(days: int = 7) -> list[dict[str, Any]]:
    cutoff = time.time() - max(1, int(days)) * 86400
    out = []
    for row in list(_request(f"{DEFILLAMA_BASE}/protocols") or []):
        listed = row.get("listedAt")
        if listed is None:
            continue
        try:
            listed_ts = float(listed)
        except (TypeError, ValueError):
            continue
        if listed_ts >= cutoff:
            out.append(row)
    out.sort(key=lambda x: float(x.get("listedAt") or 0), reverse=True)
    return out

def get_yields(chain: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
    n = max(1, min(int(limit), 100))
    params: dict[str, Any] = {}
    if chain:
        params["chain"] = chain
    rows = list((_request(f"{YIELDS_BASE}/pools", params) or {}).get("data", []))
    rows.sort(key=lambda x: float(x.get("apy") or 0), reverse=True)
    return rows[:n]

def get_stablecoin_overview() -> list[dict[str, Any]]:
    data = _request(f"{STABLECOINS_BASE}/stablecoins", {"includePrices": "true"}) or {}
    rows = data.get("peggedAssets", data if isinstance(data, list) else [])
    return list(rows or [])
