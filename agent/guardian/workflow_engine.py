from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home

_LOCK = threading.RLock()
_WORKFLOW_HOME = get_hermes_home().resolve() / "guardian"
DB_PATH = _WORKFLOW_HOME / "workflows.db"

ENGINE_SPECS: dict[str, list[tuple[str, str]]] = {
    "general": [
        ("ASSESS", "Interpret the approved mission, inspect available Guardian capabilities, and define a concrete execution plan."),
        ("EXECUTE", "Execute the plan using available skills, plugins, browser, engineering, research, creative, and runtime tools while respecting all authorization gates."),
        ("VERIFY", "Verify outputs, side effects, errors, and evidence. Do not claim success without observable results."),
        ("DELIVER", "Package the verified result and perform only authorized external delivery/deployment actions; report blockers explicitly."),
        ("MEASURE", "Record outcome, useful telemetry, and next actions for Guardian OS.")
    ],
    "news": [
        ("RESEARCH", "Research the target topic using available intelligence and browser capabilities. Produce a source-backed brief."),
        ("CREATE", "Turn the research into original publishable content. Preserve attribution and originality; do not copy source text."),
        ("REVIEW", "Quality-control the draft for factual support, originality, compliance, and obvious errors. Return an approval-ready package."),
        ("PUBLISH", "Prepare or perform publication using available authorized publishing tools. External actions remain gated; report the exact blocker when authorization is missing."),
        ("MEASURE", "Collect available performance signals and produce a concise optimization report for the next cycle."),
    ],
    "bond": [
        ("DISCOVER", "Acquire UK/Australia HNW and sophisticated-investor prospects using available authorized lead-generation channels."),
        ("QUALIFY", "Apply the Bond qualification criteria and reject incomplete, duplicated, or obviously non-qualified prospects."),
        ("COMPLIANCE", "Run the lead through the configured compliance checks. Do not invent approvals or claims."),
        ("DELIVER", "Route only qualified leads through the configured authorized delivery path. Stop on missing BOND credentials or authorization."),
        ("MEASURE", "Record lead outcome, delivery state, and available acquisition economics for the next cycle."),
    ],
    "recovery": [
        ("DISCOVER", "Find candidate scam-recovery prospects from available authorized sources."),
        ("QUALIFY", "Validate fit, contactability, and evidence before treating a prospect as a qualified lead."),
        ("VERIFY", "Run fraud-risk and duplicate checks; do not make unsupported recovery promises."),
        ("ROUTE", "Send only qualified prospects through an authorized delivery workflow."),
        ("MEASURE", "Record outcomes and conversion signals for the next cycle."),
    ],
    "crypto": [
        ("INGEST", "Collect available market/event data through connected authorized tools."),
        ("ANALYSE", "Analyse market structure, catalysts, liquidity, and relevant signals."),
        ("SCORE", "Score opportunities with explicit evidence and uncertainty; do not fabricate prices or data."),
        ("TRACK", "Persist watch candidates and meaningful state changes for later review."),
        ("REPORT", "Produce a concise opportunity report; no capital-moving execution."),
    ],
    "polymarket": [
        ("COLLECT", "Collect available public market and wallet data."),
        ("FINGERPRINT", "Build reproducible wallet/market fingerprints from observable data only."),
        ("ANALYSE", "Run forensic analysis and identify notable patterns with evidence."),
        ("PAPER", "Generate paper-trade or research signals only; do not place live capital."),
        ("REPORT", "Summarize findings, confidence, and follow-up research targets."),
    ],
    "pumpfun": [
        ("STREAM", "Ingest available Pump.fun/public market signals through connected research tools."),
        ("DETECT", "Detect notable launches, liquidity changes, and market events."),
        ("ECONOMICS", "Evaluate fees, liquidity, slippage, and other measurable economics."),
        ("REPLAY", "Replay candidates using the available paper/research pipeline."),
        ("REPORT", "Produce research findings without live capital deployment."),
    ],
    "pionex": [
        ("RESEARCH", "Define and gather the requested quantitative strategy inputs."),
        ("BACKTEST", "Run reproducible backtests with documented assumptions and metrics."),
        ("RISK", "Evaluate drawdown, exposure, fees, liquidity, and failure conditions."),
        ("PAPER", "Run or update the paper-trading stage only."),
        ("GATE", "Check the live-execution gate and report blockers; live trading stays locked unless explicitly enabled elsewhere."),
    ],
    "media": [
        ("BRIEF", "Create a content brief for the selected audience and channel."),
        ("ASSETS", "Generate or source authorized creative assets using available media tools."),
        ("EDIT", "Assemble the content package with captions, metadata, and compliance checks."),
        ("SCHEDULE", "Prepare or perform authorized publishing/scheduling. External actions remain gated."),
        ("MEASURE", "Collect available analytics and write the next-iteration recommendations."),
    ],
    "voice": [
        ("DESIGN", "Define the call objective, dialogue, routing, and safe handoff conditions."),
        ("BUILD", "Configure the available voice/telephone components."),
        ("TEST", "Run non-destructive tests for routing, prompts, logging, and failure handling."),
        ("DEPLOY", "Deploy only through authorized account and platform connections; report blockers instead of bypassing them."),
        ("MEASURE", "Capture call outcomes, handoff rates, and operational metrics."),
    ],
    "web": [
        ("PLAN", "Turn the business idea into an implementation brief, acceptance criteria, and deployment plan."),
        ("BUILD", "Build the site using the available engineering stack."),
        ("TEST", "Run build, typecheck, and relevant functional checks."),
        ("DEPLOY", "Deploy through authorized source/deployment integrations."),
        ("MEASURE", "Check runtime status and collect available usage/conversion signals."),
    ],
}

def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def _db() -> sqlite3.Connection:
    _WORKFLOW_HOME.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS workflows (
      id TEXT PRIMARY KEY,
      engine TEXT NOT NULL,
      name TEXT NOT NULL,
      mission TEXT NOT NULL,
      profile TEXT NOT NULL,
      state TEXT NOT NULL,
      current_step INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      last_error TEXT
    );
    CREATE TABLE IF NOT EXISTS workflow_steps (
      id TEXT PRIMARY KEY,
      workflow_id TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
      step_index INTEGER NOT NULL,
      name TEXT NOT NULL,
      prompt TEXT NOT NULL,
      status TEXT NOT NULL,
      cron_job_id TEXT,
      execution_id TEXT,
      retry_count INTEGER NOT NULL DEFAULT 0,
      started_at TEXT,
      finished_at TEXT,
      error TEXT,
      UNIQUE(workflow_id, step_index)
    );
    CREATE TABLE IF NOT EXISTS workflow_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      workflow_id TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
      at TEXT NOT NULL,
      type TEXT NOT NULL,
      message TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_workflows_state ON workflows(state, updated_at);
    CREATE INDEX IF NOT EXISTS idx_workflow_steps_workflow ON workflow_steps(workflow_id, step_index);
    """)
    return conn

def create_workflow(*, engine: str, name: str, mission: str, profile: str) -> dict[str, Any]:
    engine = engine.strip().lower()
    if engine not in ENGINE_SPECS:
        raise ValueError(f"Unknown Guardian engine: {engine}")
    workflow_id = "gw_" + uuid.uuid4().hex[:14]
    now = _now()
    spec = ENGINE_SPECS[engine]
    with _LOCK:
        conn = _db()
        try:
            conn.execute(
                "INSERT INTO workflows VALUES (?, ?, ?, ?, ?, 'queued', 0, ?, ?, NULL)",
                (workflow_id, engine, name[:120], mission[:5000], profile or "default", now, now),
            )
            for index, (label, instruction) in enumerate(spec):
                prompt = (
                    "Guardian OS workflow context. "
                    f"Business engine: {name}. Mission: {mission}. "
                    f"Stage: {label}. "
                    f"Instruction: {instruction}"
                )
                conn.execute(
                    "INSERT INTO workflow_steps "
                    "(id,workflow_id,step_index,name,prompt,status) VALUES (?,?,?,?,?,?)",
                    ("gws_" + uuid.uuid4().hex[:14], workflow_id, index, label, prompt, "queued"),
                )
            conn.execute(
                "INSERT INTO workflow_events(workflow_id,at,type,message) VALUES (?,?,?,?)",
                (workflow_id, now, "created", f"Workflow created for {engine}."),
            )
            conn.commit()
            return get_workflow(workflow_id) or {}
        finally:
            conn.close()

def _row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None

def get_workflow(workflow_id: str) -> dict[str, Any] | None:
    with _LOCK:
        conn = _db()
        try:
            row = conn.execute("SELECT * FROM workflows WHERE id=?", (workflow_id,)).fetchone()
            if row is None:
                return None
            out = dict(row)
            steps = [dict(r) for r in conn.execute(
                "SELECT * FROM workflow_steps WHERE workflow_id=? ORDER BY step_index", (workflow_id,)
            ).fetchall()]
            events = [dict(r) for r in conn.execute(
                "SELECT at,type,message FROM workflow_events WHERE workflow_id=? ORDER BY id DESC LIMIT 30", (workflow_id,)
            ).fetchall()]
            out["steps"] = steps
            out["events"] = events
            return out
        finally:
            conn.close()

def list_workflows(limit: int = 50) -> list[dict[str, Any]]:
    with _LOCK:
        conn = _db()
        try:
            rows = conn.execute(
                "SELECT * FROM workflows ORDER BY updated_at DESC, id DESC LIMIT ?",
                (max(1, min(int(limit), 200)),),
            ).fetchall()
            out: list[dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                step = conn.execute(
                    "SELECT * FROM workflow_steps WHERE workflow_id=? ORDER BY step_index", (item["id"],)
                ).fetchall()
                item["steps"] = [dict(r) for r in step]
                out.append(item)
            return out
        finally:
            conn.close()

def active_workflows() -> list[dict[str, Any]]:
    return [w for w in list_workflows(200) if w["state"] in {"queued", "running", "paused"}]

def set_workflow(*, workflow_id: str, state: str | None = None, current_step: int | None = None, last_error: str | None = None) -> None:
    changes: list[str] = ["updated_at=?"]
    params: list[Any] = [_now()]
    if state is not None:
        changes.append("state=?"); params.append(state)
    if current_step is not None:
        changes.append("current_step=?"); params.append(int(current_step))
    if last_error is not None:
        changes.append("last_error=?"); params.append(last_error[:1000])
    params.append(workflow_id)
    with _LOCK:
        conn = _db()
        try:
            conn.execute(f"UPDATE workflows SET {', '.join(changes)} WHERE id=?", params)
            conn.commit()
        finally:
            conn.close()

def set_step(*, workflow_id: str, step_index: int, status: str | None = None, cron_job_id: str | None = None, execution_id: str | None = None, retry_count: int | None = None, started_at: str | None = None, finished_at: str | None = None, error: str | None = None) -> None:
    changes = []; params: list[Any] = []
    for key, value in (("status", status), ("cron_job_id", cron_job_id), ("execution_id", execution_id), ("retry_count", retry_count), ("started_at", started_at), ("finished_at", finished_at), ("error", error)):
        if value is not None:
            changes.append(f"{key}=?"); params.append(value)
    if not changes:
        return
    params.extend([workflow_id, step_index])
    with _LOCK:
        conn = _db()
        try:
            conn.execute(f"UPDATE workflow_steps SET {', '.join(changes)} WHERE workflow_id=? AND step_index=?", params)
            conn.commit()
        finally:
            conn.close()

def add_event(workflow_id: str, event_type: str, message: str) -> None:
    with _LOCK:
        conn = _db()
        try:
            conn.execute(
                "INSERT INTO workflow_events(workflow_id,at,type,message) VALUES (?,?,?,?)",
                (workflow_id, _now(), event_type[:40], message[:1000]),
            )
            conn.execute("UPDATE workflows SET updated_at=? WHERE id=?", (_now(), workflow_id))
            conn.commit()
        finally:
            conn.close()

def get_current_step(workflow_id: str) -> dict[str, Any] | None:
    workflow = get_workflow(workflow_id)
    if not workflow:
        return None
    idx = int(workflow["current_step"])
    steps = workflow.get("steps", [])
    return next((s for s in steps if int(s["step_index"]) == idx), None)
