"""Guardian Polymarket Forensics V1: read-only wallet ingestion and fingerprinting."""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://data-api.polymarket.com/v2/trades"
DEFAULT_WALLET = "0xb55fa1296e6ec55d0ce53d93b9237389f11764d4"

@dataclass(frozen=True)
class Trade:
    proxy_wallet: str
    side: str
    token_id: str
    condition_id: str
    size: float
    price: float
    timestamp: int
    title: str
    slug: str
    event_slug: str
    outcome: str
    outcome_index: int | None
    transaction_hash: str

    @property
    def notional(self) -> float:
        return self.size * self.price


def _request(params: dict[str, Any]) -> dict[str, Any]:
    query = urlencode({k: v for k, v in params.items() if v is not None})
    req = Request(
        f"{BASE_URL}?{query}",
        headers={"accept": "application/json", "User-Agent": "Guardian-Polymarket-Forensics/1.0"},
    )
    with urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_trades(wallet: str, limit: int = 500, max_pages: int = 100) -> list[Trade]:
    rows: list[Trade] = []
    cursor: str | None = None
    for _ in range(max_pages):
        payload = _request({"user": wallet, "limit": min(max(limit, 1), 1000),
                            "sortDirection": "DESC", "cursor": cursor})
        for raw in payload.get("data", []):
            rows.append(Trade(
                proxy_wallet=raw.get("proxy_wallet", ""), side=raw.get("side", ""),
                token_id=str(raw.get("token_id", "")), condition_id=raw.get("condition_id", ""),
                size=float(raw.get("size", 0)), price=float(raw.get("price", 0)),
                timestamp=int(raw.get("timestamp", 0)), title=raw.get("title", ""),
                slug=raw.get("slug", ""), event_slug=raw.get("event_slug", ""),
                outcome=raw.get("outcome", ""), outcome_index=raw.get("outcome_index"),
                transaction_hash=raw.get("transaction_hash", ""),
            ))
        page = payload.get("pagination", {})
        if not page.get("has_more") or not page.get("next_cursor"):
            break
        cursor = page["next_cursor"]
        time.sleep(0.05)
    return rows


def market_family(text: str) -> str:
    text = text.lower()
    for name in ("bitcoin", "ethereum", "solana", "xrp", "hyperliquid"):
        if name in text:
            return name
    return "other"


def timeframe_family(text: str) -> str:
    text = text.lower()
    for key in ("5m", "15m", "1h", "4h", "daily", "weekly"):
        if key in text:
            return key
    return "unknown"


def bucket_price(price: float) -> str:
    if price < 0.20: return "0-20c"
    if price < 0.40: return "20-40c"
    if price < 0.60: return "40-60c"
    if price < 0.80: return "60-80c"
    return "80-100c"


def _median(values: list[int]) -> float | None:
    if not values: return None
    values = sorted(values)
    n, mid = len(values), len(values) // 2
    return float(values[mid]) if n % 2 else (values[mid - 1] + values[mid]) / 2


def reconstruct_episodes(trades: list[Trade]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, int | None], list[Trade]] = defaultdict(list)
    for trade in trades:
        groups[(trade.condition_id, trade.outcome_index)].append(trade)
    episodes = []
    for (condition_id, outcome_index), rows in groups.items():
        rows.sort(key=lambda x: (x.timestamp, x.transaction_hash))
        shares = sum(r.size for r in rows)
        notional = sum(r.notional for r in rows)
        episodes.append({
            "condition_id": condition_id, "outcome_index": outcome_index,
            "title": rows[0].title, "outcome": rows[0].outcome,
            "fills": len(rows), "buy_fills": sum(r.side == "BUY" for r in rows),
            "sell_fills": sum(r.side == "SELL" for r in rows), "shares": round(shares, 8),
            "notional_usdc": round(notional, 8),
            "vwap": round(notional / shares, 8) if shares else None,
            "first_timestamp": rows[0].timestamp, "last_timestamp": rows[-1].timestamp,
            "duration_seconds": rows[-1].timestamp - rows[0].timestamp,
        })
    return sorted(episodes, key=lambda x: (x["first_timestamp"], x["condition_id"]))


def fingerprint(trades: list[Trade]) -> dict[str, Any]:
    if not trades: return {"trade_count": 0, "markets": 0, "wallet": None}
    ordered = sorted(trades, key=lambda t: (t.timestamp, t.transaction_hash))
    by_market: dict[str, list[Trade]] = defaultdict(list)
    for trade in ordered: by_market[trade.condition_id].append(trade)
    notional = sum(t.notional for t in ordered)
    intervals = [b.timestamp - a.timestamp for a, b in zip(ordered, ordered[1:])]
    return {
        "wallet": ordered[0].proxy_wallet, "trade_count": len(ordered),
        "markets": len(by_market),
        "buy_pct": round(100 * sum(t.side == "BUY" for t in ordered) / len(ordered), 3),
        "sell_pct": round(100 * sum(t.side == "SELL" for t in ordered) / len(ordered), 3),
        "total_notional_usdc": round(notional, 6),
        "mean_trade_notional_usdc": round(notional / len(ordered), 6),
        "median_trade_interval_seconds": _median(intervals),
        "market_mix": dict(Counter(market_family(t.title) for t in ordered)),
        "timeframe_mix": dict(Counter(timeframe_family(t.slug + " " + t.title) for t in ordered)),
        "entry_price_buckets": dict(Counter(bucket_price(t.price) for t in ordered)),
        "unique_outcomes": len({(t.condition_id, t.outcome_index) for t in ordered}),
        "first_trade_utc": datetime.fromtimestamp(ordered[0].timestamp, timezone.utc).isoformat(),
        "last_trade_utc": datetime.fromtimestamp(ordered[-1].timestamp, timezone.utc).isoformat(),
    }


def save_snapshot(trades: list[Trade], fp: dict[str, Any], root: Path) -> dict[str, str]:
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    paths = {
        "raw": root / f"trades_{stamp}.json",
        "fingerprint": root / f"fingerprint_{stamp}.json",
        "episodes": root / f"episodes_{stamp}.json",
    }
    paths["raw"].write_text(json.dumps([asdict(t) for t in trades], indent=2), encoding="utf-8")
    paths["fingerprint"].write_text(json.dumps(fp, indent=2), encoding="utf-8")
    paths["episodes"].write_text(json.dumps(reconstruct_episodes(trades), indent=2), encoding="utf-8")
    return {k: str(v) for k, v in paths.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Guardian Polymarket Forensics V1")
    parser.add_argument("--wallet", default=DEFAULT_WALLET)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--pages", type=int, default=10)
    parser.add_argument("--output", default="data/polymarket_forensics/raw")
    args = parser.parse_args()
    trades = fetch_trades(args.wallet, args.limit, args.pages)
    fp = fingerprint(trades)
    paths = save_snapshot(trades, fp, Path(args.output))
    print(json.dumps({"status": "OK", "trades": len(trades), "fingerprint_summary": fp, "raw": paths["raw"], "fingerprint_file": paths["fingerprint"], "episodes": paths["episodes"]}, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
