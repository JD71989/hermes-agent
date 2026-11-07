"""Guardian operational surfaces — read-only aggregation for the dashboard.

Guardian V5's route families map onto capabilities this machine already runs:
the LEADGEN portfolio manifest and evidence ledger on disk, the engines under
``<HERMES_HOME>/automation``, the cron scheduler, the media-farm SQLite store,
the creator workspace and the vault. This module only *reads* those stores. It
never writes, never creates a database and never returns secret **values** —
credential checks report key names and a boolean only.

Every payload carries a ``source`` block (``configured``/``available``/``path``/
``updated_at``/``error``) so a surface can say "not found" instead of implying
data it could not read.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from hermes_constants import get_hermes_home

# Live trading / transfers / leverage stay off until separately authorised.
_PAPER_POLICY = {
    "mode": "paper_and_research",
    "live_trading_enabled": False,
    "withdrawals_enabled": False,
    "leverage_enabled": False,
    "requires_explicit_authorisation": True,
}

_REVENUE_JOB_RE = re.compile(
    r"revenue|bond|lead|upwork|crm|follow.?up|opportunit|economic|invoice", re.I
)
_COMMERCIAL_JOB_RE = re.compile(
    r"lead|bond|crm|follow.?up|email|outreach|upwork|market", re.I
)
_INTELLIGENCE_JOB_RE = re.compile(
    r"crypto|market|polymarket|pumpfun|quant|opportunit|research|intel", re.I
)
_CREATOR_JOB_RE = re.compile(
    r"media|youtube|content|social|editorial|writing|creator|viral", re.I
)
_MARKETING_JOB_RE = re.compile(
    r"marketing|traffic|growth|distribution|social|email|seo|news|editorial", re.I
)
_CRYPTO_JOB_RE = re.compile(r"crypto|token|snipe|solana|pumpfun", re.I)
_TRADING_JOB_RE = re.compile(r"trading|pumpfun|pionex|polymarket|quant|paper", re.I)
_CYBERLAB_JOB_RE = re.compile(r"cyber|security|audit|doctor|physical", re.I)
_AUTOMATION_JOB_RE = re.compile(r"automation|workflow|guardian|watcher|mission", re.I)

_CAPABILITIES: tuple[dict[str, Any], ...] = (
    {
        "id": "bond_revenue",
        "label": "Bond revenue (UK/AU)",
        "module": "tools.bond_revenue_tool",
        "credentials": ["BOND_API_KEY"],
    },
    {
        "id": "crypto_market_intel",
        "label": "Crypto market intelligence",
        "module": "tools.crypto_market_intel",
        "credentials": [],
    },
    {
        "id": "crypto_opportunity_discover",
        "label": "Crypto opportunity discovery",
        "module": "tools.crypto_opportunity_discover",
        "credentials": [],
    },
    {
        "id": "crypto_opportunity_score",
        "label": "Crypto opportunity scoring",
        "module": "tools.crypto_opportunity_score",
        "credentials": [],
    },
    {
        "id": "crypto_opportunity_track",
        "label": "Crypto opportunity tracking",
        "module": "tools.crypto_opportunity_track",
        "credentials": [],
    },
    {
        "id": "media_farm",
        "label": "Media farm / creator distribution",
        "module": "tools.media_farm_db",
        "credentials": [],
    },
)

_STORAGE_CACHE: dict[str, Any] = {"at": 0.0, "payload": None}
_STORAGE_TTL_S = 60.0
# The integrity sweep walks every database in the home (PRAGMA integrity_check)
# and takes minutes on a large one, so it is an explicit operator action with a
# long cache rather than part of the storage read.
_DB_HEALTH_CACHE: dict[str, Any] = {"at": 0.0, "payload": None}
_DB_HEALTH_TTL_S = 900.0


# ---------------------------------------------------------------------------
# Small read helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_from_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _read_json(path: Path) -> tuple[Any, Optional[str]]:
    """Read JSON tolerantly (BOM, trailing noise is still an error)."""
    try:
        with path.open("r", encoding="utf-8-sig") as fh:
            return json.load(fh), None
    except FileNotFoundError:
        return None, "missing"
    except Exception as exc:  # unreadable / malformed store
        return None, f"{type(exc).__name__}: {exc}"


def _source(path: Optional[Path], *, data: Any = None, error: Optional[str] = None) -> dict[str, Any]:
    if path is None:
        return {
            "configured": False,
            "available": False,
            "path": None,
            "updated_at": None,
            "size_bytes": 0,
            "error": error or "not found",
        }
    exists = path.exists()
    updated_at = None
    size = 0
    if exists:
        try:
            st = path.stat()
            updated_at = _iso_from_ts(st.st_mtime)
            size = st.st_size
        except OSError:
            pass
    return {
        "configured": True,
        "available": exists and error is None,
        "path": str(path),
        "updated_at": updated_at,
        "size_bytes": size,
        "error": error if error is not None else (None if exists else "missing"),
    }


def _read_source(path: Optional[Path], default: Any = None) -> tuple[Any, dict[str, Any]]:
    if path is None:
        return default, _source(None)
    data, error = _read_json(path)
    return (data if error is None else default), _source(path, data=data, error=error)


def _first_existing(candidates: list[Path]) -> Optional[Path]:
    for candidate in candidates:
        try:
            if candidate.is_dir():
                return candidate
        except OSError:
            continue
    return None


def _automation_home() -> Path:
    return get_hermes_home() / "automation"


def _revenue_root() -> Optional[Path]:
    """Locate the LEADGEN checkout without hardcoding a profile home.

    ``guardian.revenue_root`` in config.yaml wins (same read pattern as
    ``guardian.storage``), then the conventional Desktop locations.
    """
    configured: Optional[Path] = None
    try:
        from hermes_cli.config import load_config_readonly
        from hermes_cli.config import cfg_get

        raw = cfg_get(load_config_readonly(), "guardian", "revenue_root")
        if isinstance(raw, str) and raw.strip():
            configured = Path(os.path.expanduser(raw.strip()))
    except Exception:
        configured = None

    candidates = [
        p
        for p in (
            configured,
            Path.home() / "OneDrive" / "Desktop" / "LEADGEN",
            Path.home() / "Desktop" / "LEADGEN",
            Path.home() / "OneDrive" / "Documents" / "LEADGEN",
            Path.home() / "Documents" / "LEADGEN",
        )
        if p is not None
    ]
    return _first_existing(candidates)


def _credential_names() -> set[str]:
    """Key names present in os.environ or the profile ``.env`` — never values."""
    names = {key for key in os.environ if key}
    env_file = get_hermes_home() / ".env"
    try:
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key = line.split("=", 1)[0].strip()
            if key and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                names.add(key)
    except OSError:
        pass
    return names


def _module_present(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except Exception:
        return False


def _capabilities(credentials: set[str]) -> list[dict[str, Any]]:
    rows = []
    for spec in _CAPABILITIES:
        required = list(spec["credentials"])
        rows.append(
            {
                "id": spec["id"],
                "label": spec["label"],
                "module": spec["module"],
                "present": _module_present(spec["module"]),
                "required_credentials": required,
                "credentials_present": all(k in credentials for k in required),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Cron
# ---------------------------------------------------------------------------


def _schedule_text(job: dict[str, Any]) -> str:
    schedule = job.get("schedule")
    if isinstance(schedule, dict):
        return str(schedule.get("display") or schedule.get("expr") or "")
    return str(schedule or "")


def _job_row(job: dict[str, Any]) -> dict[str, Any]:
    execution = job.get("latest_execution") if isinstance(job.get("latest_execution"), dict) else {}
    return {
        "id": str(job.get("id") or ""),
        "name": str(job.get("name") or ""),
        "enabled": bool(job.get("enabled", True)),
        "schedule": _schedule_text(job),
        "last_status": execution.get("status") or execution.get("state"),
        "last_run": execution.get("finished_at") or execution.get("started_at"),
    }


def _matching_jobs(pattern: re.Pattern[str], limit: int = 12) -> list[dict[str, Any]]:
    try:
        from cron.jobs import list_jobs

        jobs = list_jobs(include_disabled=True)
    except Exception:
        return []
    matched = [j for j in jobs if pattern.search(str(j.get("name") or ""))]
    matched.sort(key=lambda j: (not j.get("enabled", True), str(j.get("name") or "").lower()))
    return [_job_row(j) for j in matched[:limit]]


# ---------------------------------------------------------------------------
# Portfolio / revenue
# ---------------------------------------------------------------------------


def _experiment_counts(experiments: list[dict[str, Any]]) -> dict[str, int]:
    states = Counter()
    for row in experiments:
        state = str(row.get("effective_state") or row.get("state") or "UNKNOWN").upper()
        states[state] += 1
    return dict(sorted(states.items()))


def revenue_surface() -> dict[str, Any]:
    root = _revenue_root()
    automation = _automation_home()
    credentials = _credential_names()

    portfolio_path = root / "guardian_portfolio_experiments.json" if root else None
    portfolio, portfolio_src = _read_source(portfolio_path, default={})
    experiments = portfolio.get("experiments") if isinstance(portfolio, dict) else None
    if not isinstance(experiments, list):
        experiments = []
    clean_experiments = [
        {
            "id": str(row.get("id") or ""),
            "name": str(row.get("name") or ""),
            "state": str(row.get("state") or "UNKNOWN"),
            "effective_state": row.get("effective_state"),
            "tier": row.get("tier") or None,
            "reason": row.get("reason") or None,
            "model_profile": row.get("model_profile") or None,
        }
        for row in experiments
        if isinstance(row, dict)
    ]

    manifest_path = automation / "revenue_fabric" / "activation_manifest.json"
    manifest, manifest_src = _read_source(manifest_path, default={})
    engines = manifest.get("engines") if isinstance(manifest, dict) else None
    targets = manifest.get("campaign_targets") if isinstance(manifest, dict) else None

    queue_path = automation / "opportunity_intelligence" / "actionable_queue_v3.json"
    queue, queue_src = _read_source(queue_path, default={})
    live_path = automation / "opportunity_intelligence" / "live_revenue_targets.json"
    live, live_src = _read_source(live_path, default={})
    last_run_path = automation / "opportunity_intelligence" / "last_run.json"
    last_run, last_run_src = _read_source(last_run_path, default={})

    approvals_path = automation / "approvals" / "queue.json"
    approvals, approvals_src = _read_source(approvals_path, default=[])
    approval_rows = approvals if isinstance(approvals, list) else []
    pending = [a for a in approval_rows if isinstance(a, dict) and str(a.get("status", "")).upper() in {"PENDING", "OPEN", "AWAITING_APPROVAL"}]

    evidence_path = root / "data" / "revenue_evidence.jsonl" if root else None
    evidence_rows: list[dict[str, Any]] = []
    evidence_error: Optional[str] = None
    if evidence_path is None:
        evidence_error = "not found"
    elif not evidence_path.exists():
        evidence_error = "missing"
    else:
        try:
            for line in evidence_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    if isinstance(row, dict):
                        evidence_rows.append(row)
        except Exception as exc:
            evidence_error = f"{type(exc).__name__}: {exc}"

    latest_by_lead: dict[str, dict[str, Any]] = {}
    for row in evidence_rows:
        latest_by_lead[str(row.get("lead_id"))] = row
    verified: dict[str, float] = {}
    for row in latest_by_lead.values():
        if str(row.get("event", "")).upper() != "PAID":
            continue
        try:
            amount = float(row.get("amount"))
        except (TypeError, ValueError):
            continue
        currency = str(row.get("currency") or "GBP").upper()
        verified[currency] = round(verified.get(currency, 0.0) + amount, 2)

    return {
        "generated_at": _now_iso(),
        "policy": (portfolio.get("policy") if isinstance(portfolio, dict) else None) or _PAPER_POLICY,
        "portfolio": {
            "source": portfolio_src,
            "counts": {
                "total": len(clean_experiments),
                **_experiment_counts(clean_experiments),
            },
            "experiments": clean_experiments,
        },
        "revenue_fabric": {
            "source": manifest_src,
            "mode": manifest.get("mode") if isinstance(manifest, dict) else None,
            "principle": manifest.get("principle") if isinstance(manifest, dict) else None,
            "engines": [e for e in (engines or []) if isinstance(e, dict)],
            "campaign_targets": [t for t in (targets or []) if isinstance(t, dict)],
        },
        "opportunities": {
            "source": queue_src,
            "status": queue.get("status") if isinstance(queue, dict) else None,
            "verified_revenue_usd": queue.get("verified_revenue_usd") if isinstance(queue, dict) else None,
            "external_submissions": queue.get("external_submissions") if isinstance(queue, dict) else None,
            "approval_rule": queue.get("approval_rule") if isinstance(queue, dict) else None,
            "items": [o for o in (queue.get("opportunities") or []) if isinstance(o, dict)],
            "live_targets": {
                "source": live_src,
                "status": live.get("status") if isinstance(live, dict) else None,
                "items": [t for t in (live.get("targets") or []) if isinstance(t, dict)],
            },
            "last_run": {
                "source": last_run_src,
                "status": last_run.get("status") if isinstance(last_run, dict) else None,
                "count": last_run.get("count") if isinstance(last_run, dict) else None,
                "generated_at": last_run.get("generated_at") if isinstance(last_run, dict) else None,
            },
        },
        "evidence": {
            "source": _source(evidence_path, error=evidence_error),
            "records": len(evidence_rows),
            "leads": len(latest_by_lead),
            "paid_totals": verified,
            "verified": bool(verified),
            "note": (
                "Local evidence ledger — operator assertions, not independently verified proof."
                if evidence_path is not None and evidence_error is None
                else "No revenue evidence ledger found; verified revenue is £0."
            ),
        },
        "approvals": {
            "source": approvals_src,
            "total": len(approval_rows),
            "pending": len(pending),
            "items": pending[:20],
        },
        "automation": {"jobs": _matching_jobs(_REVENUE_JOB_RE)},
        "capabilities": _capabilities(credentials),
    }


# ---------------------------------------------------------------------------
# Commercial
# ---------------------------------------------------------------------------


def commercial_surface() -> dict[str, Any]:
    automation = _automation_home()
    root = _revenue_root()
    credentials = _credential_names()

    crm_path = automation / "crm" / "contacts.json"
    crm, crm_src = _read_source(crm_path, default={})
    contacts = crm.get("contacts") if isinstance(crm, dict) else None
    contact_rows = [c for c in (contacts or []) if isinstance(c, dict)]
    by_status = dict(sorted(Counter(str(c.get("status") or "UNKNOWN") for c in contact_rows).items()))

    manifest_path = automation / "revenue_fabric" / "activation_manifest.json"
    manifest, manifest_src = _read_source(manifest_path, default={})
    targets = manifest.get("campaign_targets") if isinstance(manifest, dict) else None

    work_path = automation / "queue" / "work_queue.json"
    work, work_src = _read_source(work_path, default={})
    queued = [q for q in ((work.get("queue") if isinstance(work, dict) else None) or []) if isinstance(q, dict)]

    lead_assets = []
    if root is not None:
        for key, label, rel in (
            ("claim2aim", "Claim2Aim (investment-loss leads)", "claim2aim-clean"),
            ("bond_hnw", "HNW bond lead engine (UK/AU)", "HNW_Lead_Engine_V2_Telegram_GSheets"),
            ("garden", "Premium garden wellness", "premium-garden-wellness"),
            ("recovery", "Recovery / scam leads", "RECOVERY-WEB"),
            ("leadengine", "Lead engine core", "leadengine"),
        ):
            path = root / rel
            exists = path.is_dir()
            files = 0
            updated_at = None
            if exists:
                try:
                    newest = max((p.stat().st_mtime for p in path.rglob("*") if p.is_file()), default=None)
                    updated_at = _iso_from_ts(newest) if newest else None
                    files = sum(1 for p in path.rglob("*") if p.is_file())
                except OSError:
                    pass
            lead_assets.append(
                {
                    "key": key,
                    "label": label,
                    "path": str(path),
                    "exists": exists,
                    "has_public": (path / "public").is_dir(),
                    "has_netlify": (path / ".netlify").is_dir(),
                    "files": files,
                    "updated_at": updated_at,
                }
            )

    leadengine_modules: list[str] = []
    if root is not None:
        try:
            leadengine_modules = sorted(p.stem for p in (root / "leadengine").glob("*.py") if p.is_file())
        except OSError:
            leadengine_modules = []

    delivery_path = automation / "revenue_fabric" / "campaigns" / "bond_leads" / "email_delivery.json"
    delivery, delivery_src = _read_source(delivery_path, default={})

    return {
        "generated_at": _now_iso(),
        "revenue_root": {
            "configured": root is not None,
            "path": str(root) if root else None,
        },
        "crm": {
            "source": crm_src,
            "contact_count": len(contact_rows),
            "by_status": by_status,
            "contacts": contact_rows[:25],
            "categories": (crm.get("meta") or {}).get("categories") if isinstance(crm, dict) else None,
        },
        "campaigns": {
            "source": manifest_src,
            "targets": [t for t in (targets or []) if isinstance(t, dict)],
        },
        "lead_queue": {
            "source": work_src,
            "total": len(queued),
            "items": queued[:15],
        },
        "lead_assets": lead_assets,
        "leadengine": {"modules": leadengine_modules},
        "bond_delivery": {
            "source": delivery_src,
            "campaign": delivery.get("campaign") if isinstance(delivery, dict) else None,
            "delivery_method": delivery.get("delivery_method") if isinstance(delivery, dict) else None,
            "status": delivery.get("status") if isinstance(delivery, dict) else None,
            "transport_status": delivery.get("transport_status") if isinstance(delivery, dict) else None,
            "sender_verification_status": delivery.get("sender_verification_status") if isinstance(delivery, dict) else None,
            "api_dependency": delivery.get("api_dependency") if isinstance(delivery, dict) else None,
        },
        "automation": {"jobs": _matching_jobs(_COMMERCIAL_JOB_RE)},
        "credentials": [
            {"name": key, "present": key in credentials}
            for key in (
                "SUPABASE_URL",
                "SUPABASE_SERVICE_ROLE_KEY",
                "TELEGRAM_BOT_TOKEN",
                "BOND_API_KEY",
                "GROQ_API_KEY",
                "OPENAI_API_KEY",
            )
        ],
    }


# ---------------------------------------------------------------------------
# Intelligence
# ---------------------------------------------------------------------------


def intelligence_surface() -> dict[str, Any]:
    automation = _automation_home()
    repo = Path(__file__).resolve().parent.parent
    credentials = _credential_names()

    queue_path = automation / "opportunity_intelligence" / "actionable_queue_v3.json"
    queue, queue_src = _read_source(queue_path, default={})
    live_path = automation / "opportunity_intelligence" / "live_revenue_targets.json"
    live, live_src = _read_source(live_path, default={})
    last_path = automation / "opportunity_intelligence" / "last_run.json"
    last, last_src = _read_source(last_path, default={})

    watch_path = automation / "markets" / "watchlist.json"
    watch, watch_src = _read_source(watch_path, default={})
    markets = watch.get("markets") if isinstance(watch, dict) else None
    if markets is None and isinstance(watch, dict):
        markets = watch.get("watchlist")

    research_dir = repo / "research"
    artifacts = []
    try:
        for path in sorted(research_dir.iterdir()):
            if not path.is_file():
                continue
            try:
                st = path.stat()
            except OSError:
                continue
            artifacts.append(
                {
                    "name": path.name,
                    "kind": path.suffix.lstrip(".") or "file",
                    "size_bytes": st.st_size,
                    "updated_at": _iso_from_ts(st.st_mtime),
                }
            )
    except OSError:
        artifacts = []

    return {
        "generated_at": _now_iso(),
        "policy": dict(_PAPER_POLICY),
        "opportunity_intelligence": {
            "queue": {
                "source": queue_src,
                "status": queue.get("status") if isinstance(queue, dict) else None,
                "verified_revenue_usd": queue.get("verified_revenue_usd") if isinstance(queue, dict) else None,
                "external_submissions": queue.get("external_submissions") if isinstance(queue, dict) else None,
                "items": [o for o in ((queue.get("opportunities") if isinstance(queue, dict) else None) or []) if isinstance(o, dict)],
            },
            "live_targets": {
                "source": live_src,
                "status": live.get("status") if isinstance(live, dict) else None,
                "items": [t for t in ((live.get("targets") if isinstance(live, dict) else None) or []) if isinstance(t, dict)],
            },
            "last_run": {
                "source": last_src,
                "generated_at": last.get("generated_at") if isinstance(last, dict) else None,
                "count": last.get("count") if isinstance(last, dict) else None,
                "status": last.get("status") if isinstance(last, dict) else None,
            },
        },
        "markets": {"source": watch_src, "watchlist": markets},
        "research": {
            "source": _source(research_dir if research_dir.is_dir() else None),
            "artifacts": artifacts,
        },
        "capabilities": _capabilities(credentials),
        "automation": {"jobs": _matching_jobs(_INTELLIGENCE_JOB_RE)},
        "workflows": _workflow_rows(),
    }


def _workflow_rows(limit: int = 10) -> list[dict[str, Any]]:
    try:
        from agent.guardian import workflow_engine

        rows = workflow_engine.list_workflows(limit=limit)
    except Exception:
        return []
    out = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "id": row.get("id"),
                "name": row.get("name"),
                "engine": row.get("engine"),
                "state": row.get("state"),
                "current_step": row.get("current_step"),
                "created_at": row.get("created_at"),
                "last_error": row.get("last_error") or None,
            }
        )
    return out


# ---------------------------------------------------------------------------
# Creators
# ---------------------------------------------------------------------------


def creators_surface() -> dict[str, Any]:
    automation = _automation_home()

    manifest_path = automation / "content" / "ai_creators" / "creator_manifest.json"
    manifest, manifest_src = _read_source(manifest_path, default={})
    creators = [c for c in ((manifest.get("creators") if isinstance(manifest, dict) else None) or []) if isinstance(c, dict)]

    campaign_path = automation / "social_creator_mesh" / "campaigns" / "social_creator_mesh_2026-11-05.json"
    campaign, campaign_src = _read_source(campaign_path, default={})
    signals_path = automation / "social_creator_mesh" / "demand_signals.json"
    signals, signals_src = _read_source(signals_path, default={})

    yt_config_path = automation / "youtube_viral_studio" / "config.json"
    yt_config, yt_config_src = _read_source(yt_config_path, default={})
    yt_last_path = automation / "youtube_viral_studio" / "daily" / "last_run.json"
    yt_last, yt_last_src = _read_source(yt_last_path, default={})

    writing_out = automation / "news_media" / "research" / "writing_revenue_opportunities.json"
    writing_queue = automation / "news_media" / "drafts" / "writing_revenue_queue.json"
    writing, writing_src = _read_source(writing_out, default={})
    queue, queue_src = _read_source(writing_queue, default={})

    media = _media_farm_counts()
    pipeline = _creator_pipeline(creators, writing, queue, media)

    return {
        "generated_at": _now_iso(),
        "creator_manifest": {
            "source": manifest_src,
            "count": manifest.get("count") if isinstance(manifest, dict) else len(creators),
            "creators": creators,
        },
        "social_mesh": {
            "campaign": {"source": campaign_src, **({k: campaign.get(k) for k in ("title", "objective", "status", "platforms", "cadence", "budget", "start_date", "end_date")} if isinstance(campaign, dict) else {})},
            "demand_signals": {
                "source": signals_src,
                "scan_date": signals.get("scan_date") if isinstance(signals, dict) else None,
                "signals": [s for s in ((signals.get("market_signals") if isinstance(signals, dict) else None) or []) if isinstance(s, dict)],
                "constraints": signals.get("constraints") if isinstance(signals, dict) else None,
            },
        },
        "youtube": {
            "config": {
                "source": yt_config_src,
                "status": yt_config.get("status") if isinstance(yt_config, dict) else None,
                "cadence": yt_config.get("cadence") if isinstance(yt_config, dict) else None,
                "formats": yt_config.get("formats") if isinstance(yt_config, dict) else None,
                "revenue_verified": yt_config.get("revenue_verified") if isinstance(yt_config, dict) else None,
                "external_publish": yt_config.get("external_publish") if isinstance(yt_config, dict) else None,
            },
            "last_run": {
                "source": yt_last_src,
                "run_date": yt_last.get("run_date") or yt_last.get("date") if isinstance(yt_last, dict) else None,
                "status": yt_last.get("status") if isinstance(yt_last, dict) else None,
            },
        },
        "writing": {
            "source": writing_src,
            "generated_at": writing.get("generated_at") if isinstance(writing, dict) else None,
            "status": writing.get("status") if isinstance(writing, dict) else None,
            "opportunities": len((writing.get("opportunities") if isinstance(writing, dict) else None) or []),
            "top": [o for o in ((writing.get("opportunities") if isinstance(writing, dict) else None) or [])[:8] if isinstance(o, dict)],
            "channels": [c for c in ((writing.get("channels") if isinstance(writing, dict) else None) or []) if isinstance(c, dict)],
            "queue": {
                "source": queue_src,
                "status": queue.get("status") if isinstance(queue, dict) else None,
                "items": len((queue.get("items") if isinstance(queue, dict) else None) or []),
            },
        },
        "media_farm": media,
        "pipeline": pipeline,
        "automation": {"jobs": _matching_jobs(_CREATOR_JOB_RE)},
    }


def _media_farm_counts() -> dict[str, Any]:
    from hermes_constants import get_hermes_home as _home

    path = _home() / "media_farm.db"
    payload: dict[str, Any] = {**_source(path if path.exists() else None)}
    if not path.exists():
        payload.update({"available": False, "counts": {}, "recent_content": []})
        return payload
    try:
        import sqlite3

        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
        try:
            tables = {
                row[0]
                for row in conn.execute("select name from sqlite_master where type='table'")
            }
            counts = {}
            for table in ("campaigns", "content", "influencers", "assets", "engagements", "conversions", "video_pipeline"):
                if table in tables:
                    counts[table] = conn.execute(f"select count(*) from {table}").fetchone()[0]
            recent: list[dict[str, Any]] = []
            if "content" in tables:
                cur = conn.execute("select title, content_type, status, updated_at from content order by updated_at desc limit 8")
                recent = [
                    {"title": r[0], "content_type": r[1], "status": r[2], "updated_at": r[3]}
                    for r in cur.fetchall()
                ]
        finally:
            conn.close()
        payload.update({"available": True, "counts": counts, "recent_content": recent})
    except Exception as exc:
        payload.update(
            {
                "available": False,
                "counts": {},
            "recent_content": [],
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
    return payload


def _creator_pipeline(
    creators: list[dict[str, Any]],
    writing: Any,
    queue: Any,
    media: dict[str, Any],
) -> list[dict[str, Any]]:
    opportunities = len((writing.get("opportunities") if isinstance(writing, dict) else None) or [])
    queued = len((queue.get("items") if isinstance(queue, dict) else None) or [])
    counts = media.get("counts") if isinstance(media, dict) else {}
    return [
        {"stage": "Creator identities", "count": len(creators), "detail": "AI creator manifest"},
        {"stage": "Writing opportunities", "count": opportunities, "detail": "news_media research"},
        {"stage": "Writing queue", "count": queued, "detail": "awaiting human publication approval"},
        {"stage": "Media campaigns", "count": int((counts or {}).get("campaigns", 0)), "detail": "media farm"},
        {"stage": "Content items", "count": int((counts or {}).get("content", 0)), "detail": "media farm"},
        {"stage": "Influencers", "count": int((counts or {}).get("influencers", 0)), "detail": "media farm"},
    ]


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def storage_surface(*, max_age_s: float = _STORAGE_TTL_S) -> dict[str, Any]:
    now = time.monotonic()
    cached = _STORAGE_CACHE.get("payload")
    if cached is not None and now - float(_STORAGE_CACHE.get("at") or 0) < max_age_s:
        return cached

    try:
        from hermes_cli.guardian_storage import get_storage_summary

        summary = get_storage_summary(include_databases=False, include_hermes_size=False)
    except Exception as exc:
        summary = {"error": f"{type(exc).__name__}: {exc}"}
    payload = {"generated_at": _now_iso(), "integrity": "not_run", **summary}
    _STORAGE_CACHE["at"] = now
    _STORAGE_CACHE["payload"] = payload
    return payload


def _all_jobs(limit: int = 30) -> list[dict[str, Any]] | None:
    try:
        from cron.jobs import list_jobs

        jobs = list_jobs(include_disabled=True)
    except Exception:
        return None
    jobs_sorted = sorted(jobs, key=lambda j: (not j.get("enabled", True), str(j.get("name") or "").lower()))
    return [_job_row(j) for j in jobs_sorted[:limit]]


def marketing_surface() -> dict[str, Any]:
    """Marketing department — traffic lanes over existing growth stores.

    Guardian V5's Traffic Engine / Growth Mesh are folded into Hermes stores:
    content via media farm + writing queue, leads via CRM, opportunities via
    the scored queue. No new funnel, no invented traffic numbers.
    """
    automation = _automation_home()
    commercial = commercial_surface()
    creators = creators_surface()
    queue_path = automation / "opportunity_intelligence" / "actionable_queue_v3.json"
    queue, queue_src = _read_source(queue_path, default={})
    opportunities = queue.get("opportunities") if isinstance(queue, dict) else None
    if not isinstance(opportunities, list):
        opportunities = []
    lanes = [
        {
            "lane": "Content Factory",
            "target": "/guardian/creators",
            "description": "Create, repurpose and distribute content.",
            "count": creators["media_farm"]["counts"].get("content", 0) if creators["media_farm"].get("available") else 0,
        },
        {
            "lane": "Creator / Influencer",
            "target": "/guardian/creators",
            "description": "Route creator workflows through the shared identity layer.",
            "count": creators["creator_manifest"]["count"] or 0,
        },
        {
            "lane": "Lead Machine",
            "target": "/guardian/commercial",
            "description": "Capture and qualify traffic into revenue.",
            "count": commercial["crm"]["contact_count"],
        },
        {
            "lane": "Analytics",
            "target": "/guardian/intelligence",
            "description": "Keep measurement and system truth visible.",
            "count": len(opportunities),
        },
    ]
    return {
        "generated_at": _now_iso(),
        "policy": dict(_PAPER_POLICY),
        "lanes": lanes,
        "funnel": {
            "opportunities": len(opportunities),
            "crm_contacts": commercial["crm"]["contact_count"],
            "writing_opportunities": creators["writing"]["opportunities"],
            "writing_queue": creators["writing"]["queue"]["items"],
            "media_content": creators["media_farm"]["counts"].get("content", 0) if creators["media_farm"].get("available") else 0,
            "campaign_targets": len(commercial["campaigns"]["targets"]),
        },
        "campaigns": {
            "social_mesh": creators["social_mesh"]["campaign"],
            "targets": commercial["campaigns"]["targets"],
        },
        "sources": {
            "opportunities": queue_src,
            "crm": commercial["crm"]["source"],
            "creators": creators["creator_manifest"]["source"],
            "media_farm": creators["media_farm"].get("source") if isinstance(creators["media_farm"], dict) else None,
        },
        "automation": {"jobs": _matching_jobs(_MARKETING_JOB_RE)},
    }


def _assess_token_demo() -> dict[str, Any]:
    """Guardian token-snipe risk gate — demo candidate, paper only.

    Ported from Guardian V5 src/lib/revenue/token-snipe.ts assessToken.
    Detector runs, live execution stays gated.
    """
    t = {
        "id": "demo",
        "symbol": "DEMO",
        "ageMinutes": 8,
        "liquidityUsd": 75000,
        "marketCapUsd": 300000,
        "volume1hUsd": 180000,
        "buys1h": 240,
        "sells1h": 90,
        "holderCount": 900,
        "top10SupplyPct": 35,
        "devSupplyPct": 3,
        "bundledSupplyPct": 5,
        "insiderSupplyPct": 4,
        "sniperSupplyPct": 8,
        "mintAuthorityDisabled": True,
        "freezeAuthorityDisabled": True,
        "creatorSoldPct": 0,
        "holderGrowth1hPct": 80,
        "volumeGrowthPct": 140,
        "smartTraderBuyPct": 25,
        "suspiciousWashScore": 5,
    }
    hard_fails: list[str] = []
    if t["liquidityUsd"] < 25000:
        hard_fails.append("liquidity-too-low")
    if t["marketCapUsd"] <= 0 or t["liquidityUsd"] / t["marketCapUsd"] < 0.10:
        hard_fails.append("liquidity-to-market-cap-too-low")
    if t["holderCount"] < 300:
        hard_fails.append("holder-count-too-low")
    if t["top10SupplyPct"] > 40:
        hard_fails.append("top10-concentration")
    if t["devSupplyPct"] > 5:
        hard_fails.append("dev-concentration")
    if t["bundledSupplyPct"] > 15:
        hard_fails.append("bundled-concentration")
    if t["insiderSupplyPct"] > 15:
        hard_fails.append("insider-concentration")
    if t["sniperSupplyPct"] > 15:
        hard_fails.append("sniper-concentration")
    if not t["mintAuthorityDisabled"]:
        hard_fails.append("mint-authority-active")
    if not t["freezeAuthorityDisabled"]:
        hard_fails.append("freeze-authority-active")
    score = 0
    if t["liquidityUsd"] >= 50000:
        score += 15
    elif t["liquidityUsd"] >= 25000:
        score += 10
    if t["holderGrowth1hPct"] >= 50:
        score += 15
    elif t["holderGrowth1hPct"] >= 20:
        score += 8
    if t["volumeGrowthPct"] >= 100:
        score += 15
    elif t["volumeGrowthPct"] >= 50:
        score += 8
    if t["buys1h"] > t["sells1h"] * 1.5:
        score += 12
    if t["smartTraderBuyPct"] >= 20:
        score += 10
    if t["ageMinutes"] <= 30:
        score += 8
    if t["ageMinutes"] <= 10:
        score += 4
    decision = "REJECT" if hard_fails else ("APPROVAL_REQUIRED" if score >= 75 else ("PAPER" if score >= 55 else "WATCH"))
    return {"symbol": t["symbol"], "score": score, "decision": decision, "hard_fails": hard_fails, "candidate": t}


def crypto_surface() -> dict[str, Any]:
    """Crypto department — Solana launch intelligence, paper only.

    No wallet movement, no live execution. Detector + risk gate only.
    """
    intelligence = intelligence_surface()
    credentials = _credential_names()
    return {
        "generated_at": _now_iso(),
        "policy": dict(_PAPER_POLICY, live_trading_enabled=False, withdrawals_enabled=False),
        "detector": {
            "status": "READY",
            "risk_gate": "ACTIVE",
            "paper_trading": "READY",
            "live_execution": "GATED",
            "demo": _assess_token_demo(),
            "signal_stack": [
                "New pools",
                "liquidity",
                "holder concentration",
                "bundler/insider/dev behaviour",
                "first buyers",
                "holder growth",
                "volume acceleration",
                "buy pressure",
                "smart-trader participation",
                "manipulation checks",
            ],
        },
        "markets": intelligence["markets"],
        "capabilities": _capabilities(credentials),
        "automation": {"jobs": _matching_jobs(_CRYPTO_JOB_RE)},
    }


def trading_surface() -> dict[str, Any]:
    """Trading department — paper research only, live locked.

    Guardian V5 pumpfun/pionex/polymarket lanes map to existing Hermes paper
    tools. Execution, leverage and withdrawals stay off.
    """
    intelligence = intelligence_surface()
    credentials = _credential_names()
    return {
        "generated_at": _now_iso(),
        "policy": dict(_PAPER_POLICY),
        "lanes": [
            {"lane": "Pump.fun", "mode": "PAPER — discovery → economics → replay → paper execution", "status": "READY"},
            {"lane": "Polymarket", "mode": "PAPER — wallet feed → fingerprinting → market intelligence", "status": "READY"},
            {"lane": "Pionex Quant", "mode": "PAPER — research → backtest → paper trading", "status": "READY"},
        ],
        "opportunity_intelligence": intelligence["opportunity_intelligence"],
        "markets": intelligence["markets"],
        "workflows": intelligence["workflows"],
        "capabilities": _capabilities(credentials),
        "automation": {"jobs": _matching_jobs(_TRADING_JOB_RE)},
    }


def cyberlab_surface() -> dict[str, Any]:
    """CyberLab department — defensive research only.

    No offensive commands, no arbitrary execution. Read-only health checks
    through existing Hermes task types.
    """
    automation = _automation_home()
    vault_path = automation / "vault" / "status.json"
    physical_path = automation / "physical_security" / "status.json"
    vault, vault_src = _read_source(vault_path, default={})
    physical, physical_src = _read_source(physical_path, default={})
    return {
        "generated_at": _now_iso(),
        "policy": {
            "mode": "defensive_research_only",
            "offensive_execution": False,
            "read_only_health_checks": True,
            "requires_explicit_authorisation": True,
        },
        "status": {
            "research_cases": "No case store exists yet",
            "threat_indicators": "No indicator feed connected",
            "findings": "No findings recorded",
            "highest_severity": "UNKNOWN",
        },
        "vault": {"source": vault_src, "status": vault.get("status") if isinstance(vault, dict) else None},
        "physical_security": {"source": physical_src, "status": physical.get("status") if isinstance(physical, dict) else None},
        "boundary": {
            "allowed": [
                "defensive research",
                "threat intelligence",
                "hardening advice",
                "read-only health checks through existing Hermes task types",
            ],
            "forbidden": ["arbitrary execution", "offensive commands", "automated testing of external targets"],
        },
        "automation": {"jobs": _matching_jobs(_CYBERLAB_JOB_RE)},
    }


def automation_surface() -> dict[str, Any]:
    """Automation department — cron, workflows, approvals, tasks.

    Reuses existing Hermes scheduler + workflow engine. No new orchestrator.
    """
    automation = _automation_home()
    approvals_path = automation / "approvals" / "queue.json"
    approvals, approvals_src = _read_source(approvals_path, default=[])
    approval_rows = approvals if isinstance(approvals, list) else []
    pending = [a for a in approval_rows if isinstance(a, dict) and str(a.get("status", "")).upper() in {"PENDING", "OPEN", "AWAITING_APPROVAL"}]
    jobs = _all_jobs(limit=50)
    workflows = _workflow_rows(limit=20)
    return {
        "generated_at": _now_iso(),
        "cron": {"jobs": jobs or [], "source": {"configured": True, "available": jobs is not None}},
        "workflows": workflows,
        "approvals": {"source": approvals_src, "total": len(approval_rows), "pending": len(pending), "items": pending[:20]},
        "automation": {"jobs": _matching_jobs(_AUTOMATION_JOB_RE)},
    }


def system_surface() -> dict[str, Any]:
    """System Administration — storage, databases, cron, health.

    Hermes native pages own config/keys/models/logs. This surface aggregates
    storage + database health + cron + gateway status without duplicating them.
    """
    storage = storage_surface()
    jobs = _all_jobs(limit=20)
    return {
        "generated_at": _now_iso(),
        "storage": storage,
        "cron": {"jobs": jobs or []},
        "links": [
            {"label": "System", "path": "/system", "description": "Hermes system page — gateway, memory, storage card"},
            {"label": "Models", "path": "/models", "description": "Model providers and assignments"},
            {"label": "Logs", "path": "/logs", "description": "Agent, errors, gateway logs"},
            {"label": "Cron", "path": "/cron", "description": "Scheduled jobs and blueprints"},
            {"label": "Skills", "path": "/skills", "description": "Skills and toolsets"},
            {"label": "Keys", "path": "/env", "description": "Secrets (key names only on this surface)"},
            {"label": "Vault", "path": "/guardian/vault", "description": "Encrypted credential control plane"},
        ],
    }


def database_health(*, max_age_s: float = _DB_HEALTH_TTL_S, force: bool = False) -> dict[str, Any]:
    """Full ``PRAGMA integrity_check`` sweep — slow, cached, operator-initiated."""
    now = time.monotonic()
    cached = _DB_HEALTH_CACHE.get("payload")
    if (
        not force
        and cached is not None
        and now - float(_DB_HEALTH_CACHE.get("at") or 0) < max_age_s
    ):
        return cached

    try:
        from hermes_cli.guardian_storage import check_all_databases

        results = check_all_databases()
        error = None
    except Exception as exc:
        results = []
        error = f"{type(exc).__name__}: {exc}"

    invalid = [r for r in results if isinstance(r, dict) and not r.get("valid")]
    payload = {
        "generated_at": _now_iso(),
        "integrity": "checked",
        "error": error,
        "count": len(results),
        "invalid": len(invalid),
        "databases": results,
    }
    _DB_HEALTH_CACHE["at"] = now
    _DB_HEALTH_CACHE["payload"] = payload
    return payload
