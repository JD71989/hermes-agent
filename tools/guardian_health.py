"""Guardian ↔ Hermes task execution.

Polls the existing Guardian command endpoint (/api/public/hermes-commands),
claims SYSTEM_HEALTH_CHECK tasks, executes a fixed read-only health check,
and submits results through the existing Guardian ACK/result mechanisms.

Do NOT create a new queue, new Guardian endpoints, or rebuild telemetry.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from hermes_constants import get_hermes_home
from tools.registry import registry
from utils import env_var_enabled

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Idempotency state (persisted to HERMES_HOME)
# ---------------------------------------------------------------------------

_guardian_task_state_path = Path(get_hermes_home()) / "guardian_task_state.json"


def _load_task_state() -> Dict[str, Any]:
    """Load the persisted task state from disk (across restarts)."""
    try:
        if _guardian_task_state_path.exists():
            with open(_guardian_task_state_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as exc:
        logger.debug("Failed to load guardian task state: %s", exc)
    return {"completed_requests": {}, "acked_requests": {}}


def _save_task_state(state: Dict[str, Any]) -> None:
    """Persist the task state to disk."""
    try:
        _guardian_task_state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(_guardian_task_state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
    except Exception as exc:
        logger.debug("Failed to save guardian task state: %s", exc)


# ---------------------------------------------------------------------------
# Health check implementation
# ---------------------------------------------------------------------------


def _run_health_check() -> Dict[str, Any]:
    """Execute the fixed read-only SYSTEM_HEALTH_CHECK.

    Reports on existing local components where safely available:
    - Hermes (version from package)
    - Platform hostname
    - Ollama (if reachable)
    - CUA (Computer Use Agent status)
    - Tailscale (if configured)

    Returns structured data equivalent to:
    {
      "ok": true/false,
      "host": "<hostname>",
      "checks": [
        {
          "subject": "<component>",
          "state": "<state>",
          "version": "<version if known>",
          "detail": "<optional>"
        }
      ],
      "failureReason": "<only on failure>"
    }
    """
    import platform as _platform_module

    hostname = _platform_module.node()
    checks: list[Dict[str, Any]] = []
    ok = True
    failure_reason: Optional[str] = None

    # Hermes version
    try:
        import hermes_agent
        version = getattr(hermes_agent, "__version__", "unknown")
        checks.append(
            {
                "subject": "hermes",
                "state": "ok",
                "version": str(version),
                "detail": "Hermes agent running",
            }
        )
    except Exception as e:
        ok = False
        failure_reason = f"Failed to determine Hermes version: {e}"
        checks.append(
            {
                "subject": "hermes",
                "state": "error",
                "detail": failure_reason,
            }
        )

    # Platform hostname
    checks.append(
        {
            "subject": "host",
            "state": "ok",
            "version": hostname,
            "detail": f"Hostname: {hostname}",
        }
    )

    # Ollama check (simple subprocess probe)
    try:
        result = subprocess.run(
            ["ollama", "ps"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            checks.append(
                {
                    "subject": "ollama",
                    "state": "ok",
                    "version": "running",
                    "detail": result.stdout.strip() or "Ollama running",
                }
            )
        else:
            checks.append(
                {
                    "subject": "ollama",
                    "state": "warn",
                    "detail": "Ollama not responding",
                }
            )
    except Exception:
        checks.append(
            {
                "subject": "ollama",
                "state": "unavailable",
                "detail": "Ollama not installed or not reachable",
            }
        )

    # Tailscale check
    try:
        result = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            import json as _json
            ts = _json.loads(result.stdout)
            if ts.DNS and ts.DNS[0].IP:
                checks.append(
                    {
                        "subject": "tailscale",
                        "state": "ok",
                        "version": ts.Self.DNSName or "connected",
                        "detail": f"Tailscale IP: {ts.DNS[0].IP}",
                    }
                )
            else:
                checks.append(
                    {
                        "subject": "tailscale",
                        "state": "warn",
                        "detail": "Tailscale connected but no DNS address",
                    }
                )
        else:
            checks.append(
                {
                    "subject": "tailscale",
                    "state": "warn",
                    "detail": "Tailscale not configured",
                }
            )
    except Exception:
        checks.append(
            {
                "subject": "tailscale",
                "state": "unavailable",
                "detail": "Tailscale not installed",
            }
        )

    # CUA (Computer Use Agent) check
    try:
        # Check if CUA-related files or state exists
        cua_path = Path(get_hermes_home()) / "cua_state.json"
        if cua_path.exists():
            with open(cua_path, "r", encoding="utf-8") as f:
                cua_data = json.load(f)
            checks.append(
                {
                    "subject": "cua",
                    "state": "ok",
                    "version": cua_data.get("version", "unknown"),
                    "detail": f"CUA state present (sessions: {cua_data.get('session_count', 0)})",
                }
            )
        else:
            checks.append(
                {
                    "subject": "cua",
                    "state": "unavailable",
                    "detail": "CUA state not found",
                }
            )
    except Exception:
        checks.append(
            {
                "subject": "cua",
                "state": "unavailable",
                "detail": "CUA check failed",
            }
        )

    result: Dict[str, Any] = {
        "ok": ok,
        "host": hostname,
        "checks": checks,
    }
    if failure_reason is not None:
        result["failureReason"] = failure_reason

    return result


# ---------------------------------------------------------------------------
# Tool handler
# ---------------------------------------------------------------------------


def handle_guardian_health_check(args: Optional[Dict[str, Any]] = None, **kwargs: Any) -> str:
    """Handle the SYSTEM_HEALTH_CHECK command from Guardian.

    This is the handler called by the tool registry when Guardian posts
    a command to /api/public/hermes-commands.

    Args:
        args: Command arguments from Guardian, expected to contain
              {"type": "SYSTEM_HEALTH_CHECK", "requestId": "<id>"}.
        **kwargs: Additional kwargs (task_id, etc.)

    Returns:
        JSON string result to send back to Guardian.
    """
    if args is None:
        args = {}

    request_id = args.get("requestId", "")
    cmd_type = args.get("type", "")

    # Only accept SYSTEM_HEALTH_CHECK
    if cmd_type != "SYSTEM_HEALTH_CHECK":
        # Reject silently - Guardian will handle the rejection
        return json.dumps(
            {"ok": False, "error": f"Unsupported command type: {cmd_type}"}
        )

    if not request_id:
        return json.dumps({"ok": False, "error": "Missing requestId"})

    # Load persisted state for idempotency
    state = _load_task_state()

    # Check if this requestId has already been completed
    completed = state.get("completed_requests", {})
    if request_id in completed:
        # Already completed - return the previously stored result
        # This makes duplicate delivery/idempotent
        already_completed = completed[request_id]
        return json.dumps(already_completed)

    # Check if this requestId has been ACK'd but not yet completed
    acked = state.get("acked_requests", {})
    if request_id in acked:
        # Already ACK'd but not completed - treat as already handled
        # to prevent duplicate execution
        return json.dumps({"ok": True, "already_acked": True})

    # Execute the fixed health check
    try:
        health_result = _run_health_check()
    except Exception as e:
        # Record failure
        state.setdefault("completed_requests", {})[request_id] = {
            "ok": False,
            "error": f"Health check execution failed: {e}",
            "failureReason": str(e),
        }
        _save_task_state(state)
        return json.dumps({"ok": False, "failureReason": f"Health check execution failed: {e}"})

    # Determine overall ok/state for the response
    all_ok = all(c.get("state") == "ok" for c in health_result.get("checks", []))
    any_failure = any(c.get("state") == "error" for c in health_result.get("checks", []))

    # Build the response payload
    response: Dict[str, Any] = {
        "ok": health_result.get("ok", all_ok),
        "host": health_result.get("host", ""),
        "checks": health_result.get("checks", []),
    }
    if "failureReason" in health_result:
        response["failureReason"] = health_result["failureReason"]

    # Persist as completed for idempotency
    state.setdefault("completed_requests", {})[request_id] = response
    # Remove from acked if it was there
    state.setdefault("acked_requests", {}).pop(request_id, None)
    _save_task_state(state)

    return json.dumps(response)


# ---------------------------------------------------------------------------
# Tool registration at module level (auto-discovered on import)
# ---------------------------------------------------------------------------

def check_fn() -> bool:
    """Check_fn for the guardian_health tool.

    Returns True when the GUARDIAN_HERMES_SECRET environment variable is set,
    indicating the environment is configured for Guardian integration.
    The actual authentication against Guardian is performed at runtime when
    polling the endpoint; this check_fn simply ensures the tool is only
    available when the required env var is present.
    """
    return bool(os.getenv("GUARDIAN_HERMES_SECRET"))


registry.register(
    name="guardian_health",
    toolset="guardian",
    schema={
        "type": "object",
        "properties": {
            "type": {"type": "string"},
            "requestId": {"type": "string"},
        },
        "required": ["type", "requestId"],
        "description": "Guardian command payload: {type, requestId}",
    },
    handler=handle_guardian_health_check,
    check_fn=check_fn,
    requires_env=["GUARDIAN_HERMES_SECRET"],
    description="Guardian health check execution",
)