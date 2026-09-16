"""Unified Security Audit Log for Guardian 2.

Thread-safe, profile-aware, append-only JSONL audit trail recording
security-relevant events with structured fields:

    WHO       — identity of the actor (user, agent, plugin, service)
    WHAT      — event type (authentication, authorization, tool call, etc.)
    WHEN      — UTC ISO-8601 timestamp
    WHY       — reason/context for the action
    ACTION    — what was attempted
    RESULT    — allowed/denied/error
    FAILURE   — error details if denied/failed

Log location: ``$HERMES_HOME/logs/guardian-audit.log``

Design follows ``hermes_cli/dashboard_auth/audit.py`` (JSONL, thread-locked,
fail-safe on write errors). This module deliberately avoids importing heavy
dependencies so it can load early in the startup sequence.
"""
from __future__ import annotations

import enum
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_write_lock = threading.Lock()

# Field names that must never appear in the log (token/secret protection).
_REDACTED_FIELDS: frozenset[str] = frozenset({
    "access_token", "refresh_token", "code", "code_verifier",
    "state", "ticket", "cookie", "Authorization", "authorization",
    "api_key", "secret", "password", "private_key", "bearer_token",
})


class AuditEvent(enum.Enum):
    """Security event types written to the audit log.

    Values are the literal ``event`` field on each JSON line.
    """

    # Authentication events
    AUTH_SUCCESS = "auth_success"
    AUTH_FAILURE = "auth_failure"
    AUTH_LOCKOUT = "auth_lockout"
    AUTH_RECOVERY = "auth_recovery"
    SESSION_CREATED = "session_created"
    SESSION_EXPIRED = "session_expired"
    SESSION_REVOKED = "session_revoked"

    # Authorization events
    AUTHZ_GRANTED = "authz_granted"
    AUTHZ_DENIED = "authz_denied"
    CAPABILITY_GRANTED = "capability_granted"
    CAPABILITY_REVOKED = "capability_revoked"

    # Tool execution events
    TOOL_EXECUTED = "tool_executed"
    TOOL_BLOCKED = "tool_blocked"
    TOOL_UNAUTHORIZED = "tool_unauthorized"

    # Agent events
    AGENT_STARTED = "agent_started"
    AGENT_STOPPED = "agent_stopped"
    AGENT_DELEGATED = "agent_delegated"
    AGENT_INTERRUPTED = "agent_interrupted"

    # Plugin events
    PLUGIN_LOADED = "plugin_loaded"
    PLUGIN_UNLOADED = "plugin_unloaded"
    PLUGIN_TOOL_REGISTERED = "plugin_tool_registered"
    PLUGIN_HOOK_BLOCKED = "plugin_hook_blocked"

    # Emergency controls
    EMERGENCY_ENGAGED = "emergency_engaged"
    EMERGENCY_DISENGAGED = "emergency_disengaged"
    EMERGENCY_OPERATION_BLOCKED = "emergency_operation_blocked"

    # Credential / secret events
    CREDENTIAL_ACCESSED = "credential_accessed"
    CREDENTIAL_DENIED = "credential_denied"
    SECRET_REDACTION_TRIGGERED = "secret_redaction_triggered"

    # Destructive / privileged operations
    DESTRUCTIVE_ACTION = "destructive_action"
    PRIVILEGED_ACTION = "privileged_action"
    FINANCIAL_ACTION = "financial_action"
    CONFIG_MODIFIED = "config_modified"

    # Security monitoring
    SECURITY_CHECK_PASSED = "security_check_passed"
    SECURITY_CHECK_FAILED = "security_check_failed"
    ANOMALY_DETECTED = "anomaly_detected"

    # Hardline overrides (LLM cannot override these)
    HARDLINE_BLOCKED = "hardline_blocked"


class SecurityAuditLog:
    """Thread-safe, append-only structured security audit log.

    Profile-aware: resolves ``$HERMES_HOME/logs/guardian-audit.log`` at
    write time so each profile gets its own audit trail.
    """

    def __init__(self) -> None:
        self._write_lock = threading.Lock()

    def _resolve_log_path(self) -> Path:
        """Resolve the audit log path for the active profile."""
        try:
            from hermes_constants import get_hermes_home
            return get_hermes_home() / "logs" / "guardian-audit.log"
        except Exception:
            return Path(os.path.expanduser("~/.hermes")) / "logs" / "guardian-audit.log"

    def log(
        self,
        event: AuditEvent,
        *,
        who: str = "unknown",
        what: Optional[str] = None,
        why: Optional[str] = None,
        action: Optional[str] = None,
        result: str = "allowed",
        failure: Optional[str] = None,
        identity_type: Optional[str] = None,
        session_id: Optional[str] = None,
        **extra: Any,
    ) -> None:
        """Append one security event to the audit log.

        Args:
            event: The security event type.
            who: Identity of the actor (user_id, agent_id, plugin_name, etc.).
            what: Human-readable description of what happened.
            why: Reason or context for the action.
            action: The action that was attempted.
            result: Outcome — ``"allowed"``, ``"denied"``, ``"error"``, or
                    ``"blocked"``.
            failure: Error details when result is denied/error/blocked.
            identity_type: One of ``"user"``, ``"agent"``, ``"plugin"``,
                          ``"service"``, ``"system"``.
            session_id: Session context if applicable.
            **extra: Additional structured fields.
        """
        # Strip any secret-like fields from extras.
        safe_extra = {
            k: v for k, v in extra.items()
            if k not in _REDACTED_FIELDS
        }
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event.value,
            "who": who,
            "what": what or event.value,
            "why": why,
            "action": action,
            "result": result,
            "failure": failure,
            "identity_type": identity_type,
            "session_id": session_id,
            **safe_extra,
        }
        # Remove None values to keep log compact.
        entry = {k: v for k, v in entry.items() if v is not None}
        line = json.dumps(entry, separators=(",", ":")) + "\n"
        path = self._resolve_log_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with self._write_lock:
                with open(path, "a", encoding="utf-8") as f:
                    f.write(line)
        except Exception as e:
            logger.warning("Guardian audit log write failed: %s", e)

    def query(
        self,
        *,
        event: Optional[AuditEvent] = None,
        who: Optional[str] = None,
        result: Optional[str] = None,
        identity_type: Optional[str] = None,
        since: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """Query recent audit log entries with optional filters.

        Reads the last ``limit`` entries and filters in-memory. For a
        production deployment this would be backed by a database; for now
        the JSONL file is small enough for in-memory filtering.
        """
        path = self._resolve_log_path()
        if not path.exists():
            return []
        entries: list[dict] = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if event and entry.get("event") != event.value:
                        continue
                    if who and entry.get("who") != who:
                        continue
                    if result and entry.get("result") != result:
                        continue
                    if identity_type and entry.get("identity_type") != identity_type:
                        continue
                    if since and entry.get("ts", "") < since:
                        continue
                    entries.append(entry)
        except Exception as e:
            logger.warning("Guardian audit log read failed: %s", e)
        # Return most recent entries first.
        return entries[-limit:]

    def count_events(
        self,
        *,
        event: Optional[AuditEvent] = None,
        result: Optional[str] = None,
        since: Optional[str] = None,
    ) -> int:
        """Count audit log entries matching the given filters."""
        return len(self.query(event=event, result=result, since=since, limit=10000))


# Module-level singleton.
audit_log_instance = SecurityAuditLog()


def audit_log(
    event: AuditEvent,
    *,
    who: str = "unknown",
    what: Optional[str] = None,
    why: Optional[str] = None,
    action: Optional[str] = None,
    result: str = "allowed",
    failure: Optional[str] = None,
    identity_type: Optional[str] = None,
    session_id: Optional[str] = None,
    **extra: Any,
) -> None:
    """Convenience function: append one security event to the audit log."""
    audit_log_instance.log(
        event,
        who=who,
        what=what,
        why=why,
        action=action,
        result=result,
        failure=failure,
        identity_type=identity_type,
        session_id=session_id,
        **extra,
    )


def query_audit_log(
    *,
    event: Optional[AuditEvent] = None,
    who: Optional[str] = None,
    result: Optional[str] = None,
    identity_type: Optional[str] = None,
    since: Optional[str] = None,
    limit: int = 100,
) -> list[dict]:
    """Convenience function: query the security audit log."""
    return audit_log_instance.query(
        event=event,
        who=who,
        result=result,
        identity_type=identity_type,
        since=since,
        limit=limit,
    )
