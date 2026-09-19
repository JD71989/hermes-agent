from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from agent.guardian import workflow_engine as store

BLOCKED = "blocked"
COMPLETED = "completed"
FAILED = "failed"

class NativeResult:
    def __init__(self, status: str, summary: str, data: Any = None, blocker: str | None = None):
        self.status = status
        self.summary = summary
        self.data = data
        self.blocker = blocker

    def payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "summary": self.summary[:2000],
            "blocker": self.blocker,
            "data": self.data,
        }

def _jsonish(value: Any) -> Any:
    if isinstance(value, (dict, list, int, float, bool)) or value is None:
        return value
    text = str(value)
    try:
        return json.loads(text)
    except Exception:
        return text[:5000]

def _dispatch(name: str, args: dict[str, Any]) -> NativeResult:
    from tools.registry import registry
    result = registry.dispatch(name, args)
    data = _jsonish(result)
    if isinstance(data, dict) and data.get("error"):
        return NativeResult(FAILED, f"{name} failed: {data['error']}", data)
    return NativeResult(COMPLETED, f"{name} completed.", data)

def _crypto(stage: str, mission: str) -> NativeResult:
    import tools.crypto_market_intel  # noqa: F401
    import tools.crypto_opportunity_discover  # noqa: F401
    import tools.crypto_opportunity_score  # noqa: F401
    import tools.crypto_opportunity_track  # noqa: F401
    import tools.crypto_event_track  # noqa: F401

    if stage == "INGEST":
        a = _dispatch("crypto_market_intel", {"query": "top_coins", "limit": 10})
        if a.status != COMPLETED:
            return a
        b = _dispatch("crypto_market_intel", {"query": "trending", "limit": 10})
        if b.status != COMPLETED:
            return b
        return NativeResult(COMPLETED, "Live public market and trending data collected.", {"market": a.data, "trending": b.data})
    if stage == "DETECT":
        return _dispatch("crypto_opportunity_discover", {"limit": 20, "max_risk_score": 0.8})
    if stage == "SCORE":
        discovered = _dispatch("crypto_opportunity_discover", {"limit": 10, "max_risk_score": 0.8})
        if discovered.status != COMPLETED:
            return discovered
        rows = discovered.data.get("opportunities", []) if isinstance(discovered.data, dict) else []
        if not rows:
            return NativeResult(COMPLETED, "No opportunities were returned by the native discovery engine.", {"count": 0})
        scored = []
        for row in rows[:5]:
            opp_id = row.get("id") or row.get("opportunity_id")
            if not opp_id:
                continue
            one = _dispatch("crypto_opportunity_score", {"opportunity_id": opp_id})
            if one.status != COMPLETED:
                return one
            scored.append(one.data)
        return NativeResult(COMPLETED, f"Scored {len(scored)} discovered opportunities.", {"scored": scored})
    if stage == "TRACK":
        return _dispatch("crypto_opportunity_track", {"action": "summary"})
    if stage == "REPORT":
        market = _dispatch("crypto_market_intel", {"query": "stablecoins", "limit": 10})
        tracked = _dispatch("crypto_opportunity_track", {"action": "summary"})
        return NativeResult(COMPLETED, "Native crypto report assembled.", {"stablecoins": market.data, "tracking": tracked.data})
    return NativeResult(BLOCKED, f"Crypto stage {stage} is not registered.", blocker="NATIVE_STAGE_NOT_REGISTERED")

def _media(stage: str, workflow: dict[str, Any]) -> NativeResult:
    import tools.media_farm_tool  # noqa: F401
    mission = str(workflow.get("mission") or "")
    name = str(workflow.get("name") or "Guardian Media Campaign")
    if stage == "BRIEF":
        return _dispatch("media_farm", {
            "action": "create_campaign",
            "name": name,
            "campaign_type": "social",
            "objective": mission[:1000],
            "audience": "Guardian-selected audience",
            "platforms": ["tiktok", "instagram", "facebook"],
            "cadence": "native-workflow",
            "voice": "Guardian OS",
            "budget": 0.0,
        })
    if stage == "ASSETS":
        return _dispatch("media_farm", {
            "action": "create_asset",
            "name": f"{name} asset brief",
            "asset_type": "image",
            "prompt": mission[:2000],
            "status": "planned",
            "tags": ["guardian", "workflow", "native"],
        })
    if stage == "EDIT":
        return _dispatch("media_farm", {
            "action": "create_content",
            "title": name,
            "content_type": "post",
            "platform": "multi",
            "status": "draft",
            "hook": mission[:300],
            "body": mission[:2000],
            "tags": ["guardian", "native-workflow"],
        })
    if stage == "SCHEDULE":
        return _dispatch("media_farm", {"action": "get_schedules", "limit": 25})
    if stage == "MEASURE":
        return _dispatch("media_farm", {"action": "top_content", "limit": 10})
    return NativeResult(BLOCKED, f"Media stage {stage} is not registered.", blocker="NATIVE_STAGE_NOT_REGISTERED")

def _polymarket(stage: str, mission: str) -> NativeResult:
    from research.polymarket_forensics import (
        DEFAULT_WALLET,
        fetch_trades,
        fingerprint,
        reconstruct_episodes,
        save_snapshot,
    )
    match = re.search(r"0x[a-fA-F0-9]{40}", mission)
    wallet = match.group(0) if match else DEFAULT_WALLET
    trades = fetch_trades(wallet, limit=500, max_pages=10)
    if stage == "COLLECT":
        fp = fingerprint(trades)
        paths = save_snapshot(trades, fp, Path("data/polymarket_forensics/raw"))
        return NativeResult(COMPLETED, f"Collected {len(trades)} public Polymarket trades.", {"fingerprint": fp, "paths": paths})
    if stage == "FINGERPRINT":
        return NativeResult(COMPLETED, "Wallet fingerprint generated from public trades.", fingerprint(trades))
    if stage == "ANALYSE":
        episodes = reconstruct_episodes(trades)
        return NativeResult(COMPLETED, f"Reconstructed {len(episodes)} market episodes.", {"episodes": episodes[:200], "count": len(episodes)})
    if stage == "PAPER":
        return NativeResult(BLOCKED, "Polymarket native engine is read-only; no native paper execution module is installed.", blocker="PAPER_EXECUTOR_NOT_PRESENT")
    if stage == "REPORT":
        fp = fingerprint(trades)
        episodes = reconstruct_episodes(trades)
        return NativeResult(COMPLETED, "Forensic report assembled from public data.", {"fingerprint": fp, "episode_count": len(episodes), "recent_episodes": episodes[-20:]})
    return NativeResult(BLOCKED, f"Polymarket stage {stage} is not registered.", blocker="NATIVE_STAGE_NOT_REGISTERED")

def _pumpfun(stage: str, mission: str) -> NativeResult:
    if stage in {"STREAM", "DETECT", "REPLAY"}:
        return NativeResult(
            BLOCKED,
            f"Pump.fun {stage.lower()} requires an active read-only Solana event collector; current repo contains the stream/replay primitives but no live collector executor.",
            blocker="PUMPFUN_COLLECTOR_NOT_PRESENT",
        )
    if stage == "ECONOMICS":
        from research.pumpfun_economics import PaperTrade, fee_breakdown
        breakdown = fee_breakdown(PaperTrade(
            side="BUY",
            notional_sol=1.0,
            market_cap_sol=1000.0,
            phase="graduated",
            slippage_bps=0.0,
            network_fee_sol=0.0,
        ))
        return NativeResult(COMPLETED, "Pump.fun fee economics executed using the native deterministic model.", breakdown.__dict__)
    if stage == "REPORT":
        from research.pumpfun_engine import RiskLimits
        return NativeResult(COMPLETED, "Pump.fun native risk limits verified; live transaction submission is absent by design.", {"risk_limits": RiskLimits().__dict__, "mode": "paper_only"})
    return NativeResult(BLOCKED, f"Pump.fun stage {stage} is not registered.", blocker="NATIVE_STAGE_NOT_REGISTERED")

def _blocked(engine: str, reason: str, blocker: str) -> NativeResult:
    return NativeResult(BLOCKED, reason, blocker=blocker)

def execute_stage(workflow: dict[str, Any]) -> NativeResult:
    engine = str(workflow.get("engine") or "").lower()
    step = store.get_current_step(str(workflow["id"]))
    if not step:
        return _blocked(engine, "Workflow has no current stage.", "NO_CURRENT_STAGE")
    stage = str(step.get("name") or "")
    mission = str(workflow.get("mission") or "")
    if engine == "crypto":
        return _crypto(stage, mission)
    if engine == "media":
        return _media(stage, workflow)
    if engine == "polymarket":
        return _polymarket(stage, mission)
    if engine == "pumpfun":
        return _pumpfun(stage, mission)
    if engine == "bond":
        return _blocked(engine, "Bond lead generation native executor is not present in this repository; external execution remains gated until the Bond service implementation and BOND_API_KEY are available.", "BOND_EXECUTOR_OR_KEY_MISSING")
    if engine == "recovery":
        return _blocked(engine, "Scam Recovery native lead-routing executor is not present in this repository.", "RECOVERY_EXECUTOR_NOT_PRESENT")
    if engine == "pionex":
        return _blocked(engine, "Pionex native research executor is not wired to a live market-data source; live trading remains locked.", "PIONEX_RESEARCH_EXECUTOR_NOT_PRESENT")
    if engine == "news":
        return _blocked(engine, "News native research/publishing executor is not present yet; do not substitute a generic LLM step for a native business engine.", "NEWS_EXECUTOR_NOT_PRESENT")
    if engine == "voice":
        return _blocked(engine, "Voice native account/telephony executor is not present yet.", "VOICE_EXECUTOR_NOT_PRESENT")
    if engine == "web":
        return _blocked(engine, "Website Factory native build/deploy executor is not wired into the Guardian backend yet.", "WEB_FACTORY_EXECUTOR_NOT_PRESENT")
    return _blocked(engine, f"No native executor is registered for engine '{engine}'.", "ENGINE_NOT_REGISTERED")

def persist_and_print(workflow: dict[str, Any]) -> int:
    result = execute_stage(workflow)
    wid = str(workflow["id"])
    step = store.get_current_step(wid)
    if not step:
        print(json.dumps(result.payload(), ensure_ascii=False))
        return 0
    idx = int(step["step_index"])
    data = result.payload()
    store.set_step(
        workflow_id=wid,
        step_index=idx,
        status=result.status,
        finished_at=store._now(),
        error=result.summary if result.status == FAILED else "",
    )
    store.add_event(
        wid,
        result.status,
        f"Stage {step['name']} native executor: {result.summary[:500]}",
    )
    with store._LOCK:
        conn = store._db()
        try:
            conn.execute(
                "UPDATE workflow_steps SET executor=?, result_json=?, result_summary=?, blocker=? WHERE workflow_id=? AND step_index=?",
                ("native", json.dumps(data, ensure_ascii=False)[:12000], result.summary[:2000], result.blocker, wid, idx),
            )
            conn.commit()
        finally:
            conn.close()
    print(json.dumps(data, ensure_ascii=False))
    return 42 if result.status == FAILED else 0
