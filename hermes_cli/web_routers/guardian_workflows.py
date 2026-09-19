from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agent.guardian import workflow_engine as store
from cron.executions import latest_execution
from hermes_cli.web_deps import late
from hermes_cli.web_routers._common import log as _log

router = APIRouter()
_call_cron_for_profile = late("_call_cron_for_profile", "hermes_cli.web_server_cron")
_fire_cron_job_for_profile = late("_fire_cron_job_for_profile", "hermes_cli.web_server_cron")
_mutate_cron_for_profile = late("_mutate_cron_for_profile", "hermes_cli.web_server_cron")
_cron_profile_home = late("_cron_profile_home", "hermes_cli.web_server_cron")

_SYNC_LOCK = threading.RLock()

class WorkflowLaunch(BaseModel):
    engine: str
    mission: str = Field(min_length=1, max_length=5000)
    name: Optional[str] = Field(default=None, max_length=120)
    profile: str = "default"

def _step_name(workflow: dict[str, Any]) -> str:
    step = store.get_current_step(workflow["id"])
    return str(step["name"]) if step else "UNKNOWN"

def _start_current_step(workflow: dict[str, Any]) -> dict[str, Any] | None:
    step = store.get_current_step(workflow["id"])
    if not step:
        store.set_workflow(workflow_id=workflow["id"], state="completed", current_step=0, last_error="")
        store.add_event(workflow["id"], "completed", "Workflow completed.")
        return store.get_workflow(workflow["id"])
    existing = step.get("cron_job_id")
    if existing and step.get("status") in {"running", "completed"}:
        return store.get_workflow(workflow["id"])
    profile = str(workflow.get("profile") or "default")
    job = _call_cron_for_profile(
        profile,
        "create_job",
        name=f"Guardian · {workflow['name']} · {step['name']}",
        prompt=step["prompt"],
        schedule="in 1m",
        deliver="local",
        paused=True,
        paused_reason="Guardian workflow controller owns execution.",
    )
    job_id = str(job["id"])
    store.set_step(
        workflow_id=workflow["id"],
        step_index=int(step["step_index"]),
        status="queued",
        cron_job_id=job_id,
        error="",
    )
    store.set_workflow(workflow_id=workflow["id"], state="running", last_error="")
    store.add_event(workflow["id"], "dispatch", f"Dispatching stage {step['name']} via {job_id}.")
    ran = _fire_cron_job_for_profile(profile, job_id, force=True)
    if not ran:
        raise RuntimeError(f"Guardian stage {step['name']} could not be claimed.")
    execution = latest_execution(job_id)
    if execution:
        store.set_step(
            workflow_id=workflow["id"],
            step_index=int(step["step_index"]),
            status="running",
            execution_id=str(execution["id"]),
            started_at=str(execution.get("started_at") or execution.get("claimed_at") or ""),
        )
        store.add_event(workflow["id"], "running", f"Stage {step['name']} is running.")
    return store.get_workflow(workflow["id"])

def _reconcile_one(workflow: dict[str, Any]) -> dict[str, Any] | None:
    if workflow.get("state") not in {"queued", "running", "paused"}:
        return workflow
    step = store.get_current_step(workflow["id"])
    if not step:
        store.set_workflow(workflow_id=workflow["id"], state="completed", last_error="")
        store.add_event(workflow["id"], "completed", "Workflow completed.")
        return store.get_workflow(workflow["id"])
    if workflow.get("state") == "paused":
        return workflow
    if not step.get("cron_job_id"):
        try:
            return _start_current_step(workflow)
        except Exception as exc:
            store.set_workflow(workflow_id=workflow["id"], state="failed", last_error=str(exc))
            store.set_step(workflow_id=workflow["id"], step_index=int(step["step_index"]), status="failed", error=str(exc), finished_at=store._now())
            store.add_event(workflow["id"], "failed", f"Stage dispatch failed: {exc}")
            return store.get_workflow(workflow["id"])

    execution = latest_execution(str(step["cron_job_id"]))
    if execution is None:
        return workflow
    status = str(execution.get("status") or "")
    if status in {"claimed", "running"}:
        if step.get("status") != "running":
            store.set_step(
                workflow_id=workflow["id"],
                step_index=int(step["step_index"]),
                status="running",
                execution_id=str(execution["id"]),
                started_at=str(execution.get("started_at") or execution.get("claimed_at") or ""),
            )
        return store.get_workflow(workflow["id"])
    if status == "completed":
        idx = int(step["step_index"])
        store.set_step(
            workflow_id=workflow["id"],
            step_index=idx,
            status="completed",
            execution_id=str(execution["id"]),
            finished_at=str(execution.get("finished_at") or store._now()),
            error="",
        )
        next_idx = idx + 1
        steps = workflow.get("steps") or []
        if next_idx >= len(steps):
            store.set_workflow(workflow_id=workflow["id"], state="completed", current_step=idx, last_error="")
            store.add_event(workflow["id"], "completed", "All workflow stages completed.")
            return store.get_workflow(workflow["id"])
        store.set_workflow(workflow_id=workflow["id"], state="running", current_step=next_idx, last_error="")
        store.add_event(workflow["id"], "advance", f"Stage {step['name']} completed; advancing to {steps[next_idx]['name']}.")
        try:
            return _start_current_step(store.get_workflow(workflow["id"]) or workflow)
        except Exception as exc:
            store.set_workflow(workflow_id=workflow["id"], state="failed", last_error=str(exc))
            store.set_step(workflow_id=workflow["id"], step_index=next_idx, status="failed", error=str(exc), finished_at=store._now())
            store.add_event(workflow["id"], "failed", f"Next-stage dispatch failed: {exc}")
            return store.get_workflow(workflow["id"])
    if status == "failed":
        idx = int(step["step_index"])
        error = str(execution.get("error") or "Stage execution failed.")
        store.set_step(
            workflow_id=workflow["id"],
            step_index=idx,
            status="failed",
            execution_id=str(execution["id"]),
            finished_at=str(execution.get("finished_at") or store._now()),
            error=error,
        )
        store.set_workflow(workflow_id=workflow["id"], state="failed", last_error=error)
        store.add_event(workflow["id"], "failed", f"Stage {step['name']} failed: {error}")
        return store.get_workflow(workflow["id"])
    if status == "unknown":
        error = str(execution.get("error") or "Execution outcome became unknown after owner exit.")
        idx = int(step["step_index"])
        store.set_step(workflow_id=workflow["id"], step_index=idx, status="failed", execution_id=str(execution["id"]), error=error, finished_at=store._now())
        store.set_workflow(workflow_id=workflow["id"], state="failed", last_error=error)
        store.add_event(workflow["id"], "failed", f"Stage {step['name']} is unknown; manual retry required.")
        return store.get_workflow(workflow["id"])
    return workflow

def reconcile_all() -> None:
    with _SYNC_LOCK:
        for workflow in store.active_workflows():
            try:
                _reconcile_one(workflow)
            except Exception:
                _log.exception("Guardian workflow reconciliation failed for %s", workflow.get("id"))

def _controller_loop() -> None:
    while True:
        try:
            reconcile_all()
        except Exception:
            _log.exception("Guardian workflow controller loop failed")
        time.sleep(5)

_controller_thread = threading.Thread(target=_controller_loop, name="guardian-workflow-controller", daemon=True)
_controller_thread.start()

@router.get("/api/guardian/workflow-engines")
async def workflow_engines():
    return {
        "engines": [
            {"id": key, "stages": [{"name": n} for n, _ in steps]}
            for key, steps in store.ENGINE_SPECS.items()
        ]
    }

@router.get("/api/guardian/workflows")
async def list_workflows(limit: int = 50):
    await asyncio.to_thread(reconcile_all)
    return {"workflows": await asyncio.to_thread(store.list_workflows, limit)}

@router.get("/api/guardian/workflows/{workflow_id}")
async def get_workflow(workflow_id: str):
    await asyncio.to_thread(reconcile_all)
    item = await asyncio.to_thread(store.get_workflow, workflow_id)
    if not item:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return item

@router.post("/api/guardian/workflows")
async def launch_workflow(body: WorkflowLaunch):
    engine = body.engine.strip().lower()
    if engine not in store.ENGINE_SPECS:
        raise HTTPException(status_code=400, detail=f"Unknown Guardian engine: {engine}")
    profile = (body.profile or "default").strip() or "default"
    name = (body.name or f"{engine.title()} Workflow").strip()
    workflow = await asyncio.to_thread(
        store.create_workflow,
        engine=engine,
        name=name,
        mission=body.mission.strip(),
        profile=profile,
    )
    try:
        started = await asyncio.to_thread(_start_current_step, workflow)
        return started or workflow
    except Exception as exc:
        await asyncio.to_thread(store.set_workflow, workflow_id=workflow["id"], state="failed", last_error=str(exc))
        await asyncio.to_thread(store.add_event, workflow["id"], "failed", f"Workflow start failed: {exc}")
        raise HTTPException(status_code=502, detail="Workflow created but the first stage could not be started.") from exc

@router.post("/api/guardian/workflows/{workflow_id}/pause")
async def pause_workflow(workflow_id: str):
    workflow = await asyncio.to_thread(store.get_workflow, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    step = store.get_current_step(workflow_id)
    if step and step.get("cron_job_id"):
        try:
            _mutate_cron_for_profile(str(workflow.get("profile") or "default"), "pause_job", step["cron_job_id"])
        except Exception:
            _log.debug("pause of current Guardian cron stage failed", exc_info=True)
    await asyncio.to_thread(store.set_workflow, workflow_id=workflow_id, state="paused")
    await asyncio.to_thread(store.add_event, workflow_id, "paused", f"Workflow paused at {_step_name(workflow)}.")
    return await asyncio.to_thread(store.get_workflow, workflow_id)

@router.post("/api/guardian/workflows/{workflow_id}/resume")
async def resume_workflow(workflow_id: str):
    workflow = await asyncio.to_thread(store.get_workflow, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    step = store.get_current_step(workflow_id)
    if not step:
        raise HTTPException(status_code=409, detail="Workflow has no current stage.")
    await asyncio.to_thread(store.set_workflow, workflow_id=workflow_id, state="running", last_error="")
    try:
        if step.get("cron_job_id"):
            _mutate_cron_for_profile(str(workflow.get("profile") or "default"), "resume_job", step["cron_job_id"])
            _fire_cron_job_for_profile(str(workflow.get("profile") or "default"), step["cron_job_id"], force=True)
        else:
            _start_current_step(await asyncio.to_thread(store.get_workflow, workflow_id) or workflow)
        await asyncio.to_thread(store.add_event, workflow_id, "resumed", f"Workflow resumed at {step['name']}.")
    except Exception as exc:
        await asyncio.to_thread(store.set_workflow, workflow_id=workflow_id, state="failed", last_error=str(exc))
        await asyncio.to_thread(store.add_event, workflow_id, "failed", f"Resume failed: {exc}")
        raise HTTPException(status_code=502, detail="Workflow resume failed.") from exc
    return await asyncio.to_thread(store.get_workflow, workflow_id)

@router.post("/api/guardian/workflows/{workflow_id}/retry")
async def retry_workflow(workflow_id: str):
    workflow = await asyncio.to_thread(store.get_workflow, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    step = store.get_current_step(workflow_id)
    if not step or step.get("status") != "failed":
        raise HTTPException(status_code=409, detail="Only a failed current stage can be retried.")
    count = int(step.get("retry_count") or 0) + 1
    await asyncio.to_thread(
        store.set_step,
        workflow_id=workflow_id,
        step_index=int(step["step_index"]),
        status="queued",
        cron_job_id=None,
        execution_id=None,
        retry_count=count,
        started_at="",
        finished_at="",
        error="",
    )
    await asyncio.to_thread(store.set_workflow, workflow_id=workflow_id, state="running", last_error="")
    await asyncio.to_thread(store.add_event, workflow_id, "retry", f"Retrying stage {step['name']} (attempt {count + 1}).")
    refreshed = await asyncio.to_thread(store.get_workflow, workflow_id)
    started = await asyncio.to_thread(_start_current_step, refreshed or workflow)
    return started or refreshed

@router.post("/api/guardian/workflows/{workflow_id}/cancel")
async def cancel_workflow(workflow_id: str):
    workflow = await asyncio.to_thread(store.get_workflow, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    step = store.get_current_step(workflow_id)
    if step and step.get("cron_job_id"):
        try:
            _mutate_cron_for_profile(str(workflow.get("profile") or "default"), "pause_job", step["cron_job_id"])
        except Exception:
            _log.debug("cancel pause of current Guardian cron stage failed", exc_info=True)
    await asyncio.to_thread(store.set_workflow, workflow_id=workflow_id, state="canceled")
    await asyncio.to_thread(store.add_event, workflow_id, "canceled", "Workflow canceled by operator.")
    return await asyncio.to_thread(store.get_workflow, workflow_id)
