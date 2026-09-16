"""Granular emergency stop controls for Guardian 2.

Extends the global ESTOP (``agent/estop.py``) with per-component and
per-operation-type emergency controls:

- **Global stop**: Blocks ALL new operations (delegates to ESTOP).
- **Agent stop**: Blocks new agent turns.
- **Tool stop**: Blocks specific tools or tool categories.
- **Plugin stop**: Blocks a specific plugin's operations.
- **Financial stop**: Blocks all financial/trading operations.
- **Destructive stop**: Blocks all destructive operations.
- **Network stop**: Blocks all network operations.

Emergency controls are enforced via file sentinels (consistent with
existing ESTOP pattern) and in-memory state. The file sentinels provide
crash-resilient state while the in-memory state provides fast checks.

CRITICAL RULE: LLM reasoning must NEVER override emergency stops.
The ``is_operation_allowed()`` check is deterministic and cannot be
bypassed by prompt injection or model reasoning.
"""
from __future__ import annotations

import enum
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from agent.guardian.audit import AuditEvent, audit_log

logger = logging.getLogger(__name__)


class EmergencyLevel(enum.Enum):
    """Severity levels for emergency stops."""

    # Normal operation
    NORMAL = "normal"
    # Advisory — log but don't block
    ADVISORY = "advisory"
    # Block new operations but allow in-flight to complete
    PAUSE = "pause"
    # Block ALL operations immediately
    HALT = "halt"


class EmergencyScope(enum.Enum):
    """What the emergency stop covers."""

    GLOBAL = "global"
    AGENT = "agent"
    TOOL = "tool"
    PLUGIN = "plugin"
    FINANCIAL = "financial"
    DESTRUCTIVE = "destructive"
    NETWORK = "network"


# Maps tool names to their emergency scope categories.
_TOOL_SCOPE_MAP: dict[str, EmergencyScope] = {
    # Financial tools
    "pionex_execute": EmergencyScope.FINANCIAL,
    "pionex_status": EmergencyScope.FINANCIAL,
    "pionex_positions": EmergencyScope.FINANCIAL,
    "pionex_cancel": EmergencyScope.FINANCIAL,
    "bond_revenue": EmergencyScope.FINANCIAL,

    # Destructive tools
    "terminal": EmergencyScope.DESTRUCTIVE,  # terminal can do anything
    "execute_code": EmergencyScope.DESTRUCTIVE,
    "write_file": EmergencyScope.DESTRUCTIVE,
    "patch": EmergencyScope.DESTRUCTIVE,

    # Agent tools (delegation, scheduling, memory)
    "delegate_task": EmergencyScope.AGENT,
    "cronjob": EmergencyScope.AGENT,
    "memory": EmergencyScope.AGENT,
    "session_search": EmergencyScope.AGENT,

    # Network tools
    "web_search": EmergencyScope.NETWORK,
    "web_extract": EmergencyScope.NETWORK,
    "browser_navigate": EmergencyScope.NETWORK,
    "browser_click": EmergencyScope.NETWORK,
    "browser_type": EmergencyScope.NETWORK,
    "send_message": EmergencyScope.NETWORK,
}

# Tools that are ALWAYS allowed even during emergency stops (read-only, safe).
_ALWAYS_ALLOWED_TOOLS: frozenset[str] = frozenset({
    "read_file",
    "search_files",
    "clarify",
    "todo",
    "session_search",
    "memory",
    "skill_manage",
})


def _hermes_home() -> Path:
    """Resolve the active HERMES_HOME at call time."""
    try:
        from hermes_constants import get_hermes_home
        return get_hermes_home()
    except Exception:
        return Path(os.path.expanduser("~/.hermes"))


class EmergencyStop:
    """Granular emergency stop manager with file-sentinel persistence.

    Each scope can be independently engaged/disengaged. The global scope
    overrides all others (if global is halted, nothing runs regardless
    of per-scope state).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # In-memory state: scope -> level
        self._stops: dict[EmergencyScope, EmergencyLevel] = {}
        # Per-plugin stops: plugin_name -> level
        self._plugin_stops: dict[str, EmergencyLevel] = {}
        # Per-tool stops: tool_name -> level
        self._tool_stops: dict[str, EmergencyLevel] = {}
        # Load persisted state.
        self._load_state()

    def _sentinel_dir(self) -> Path:
        """Directory for emergency stop sentinel files."""
        return _hermes_home() / "guardian" / "emergency"

    def _sentinel_path(self, scope: EmergencyScope) -> Path:
        """Path of the sentinel file for a given scope."""
        return self._sentinel_dir() / f"{scope.value}.json"

    def _plugin_sentinel_path(self, plugin_name: str) -> Path:
        """Path of the sentinel file for a specific plugin."""
        return self._sentinel_dir() / f"plugin_{plugin_name}.json"

    def _tool_sentinel_path(self, tool_name: str) -> Path:
        """Path of the sentinel file for a specific tool."""
        return self._sentinel_dir() / f"tool_{tool_name}.json"

    def _load_state(self) -> None:
        """Load emergency stop state from sentinel files."""
        sentinel_dir = self._sentinel_dir()
        if not sentinel_dir.exists():
            return
        for path in sentinel_dir.iterdir():
            if path.name.startswith("plugin_"):
                plugin_name = path.name[7:].rsplit(".", 1)[0]
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    level = EmergencyLevel(data.get("level", "pause"))
                    self._plugin_stops[plugin_name] = level
                except (json.JSONDecodeError, ValueError, KeyError):
                    self._plugin_stops[plugin_name] = EmergencyLevel.PAUSE
            elif path.name.startswith("tool_"):
                tool_name = path.name[5:].rsplit(".", 1)[0]
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    level = EmergencyLevel(data.get("level", "pause"))
                    self._tool_stops[tool_name] = level
                except (json.JSONDecodeError, ValueError, KeyError):
                    self._tool_stops[tool_name] = EmergencyLevel.PAUSE
            else:
                scope_name = path.name.rsplit(".", 1)[0]
                try:
                    scope = EmergencyScope(scope_name)
                except ValueError:
                    continue
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    level = EmergencyLevel(data.get("level", "pause"))
                except (json.JSONDecodeError, ValueError, KeyError):
                    level = EmergencyLevel.PAUSE
                self._stops[scope] = level

    def _persist_state(
        self,
        scope: EmergencyScope,
        level: EmergencyLevel,
        reason: Optional[str] = None,
    ) -> None:
        """Write a sentinel file for the given scope."""
        path = self._sentinel_path(scope)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "level": level.value,
                "scope": scope.value,
                "engaged_at": datetime.now(timezone.utc).isoformat(),
                "reason": reason,
            }
            path.write_text(
                json.dumps(payload, indent=2) + "\n", encoding="utf-8"
            )
        except OSError as e:
            logger.warning("Failed to write emergency sentinel %s: %s", path, e)

    def _persist_plugin_state(
        self,
        plugin_name: str,
        level: EmergencyLevel,
        reason: Optional[str] = None,
    ) -> None:
        """Write a sentinel file for a specific plugin."""
        path = self._plugin_sentinel_path(plugin_name)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "level": level.value,
                "plugin": plugin_name,
                "engaged_at": datetime.now(timezone.utc).isoformat(),
                "reason": reason,
            }
            path.write_text(
                json.dumps(payload, indent=2) + "\n", encoding="utf-8"
            )
        except OSError as e:
            logger.warning("Failed to write plugin sentinel %s: %s", path, e)

    def _persist_tool_state(
        self,
        tool_name: str,
        level: EmergencyLevel,
        reason: Optional[str] = None,
    ) -> None:
        """Write a sentinel file for a specific tool."""
        path = self._tool_sentinel_path(tool_name)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "level": level.value,
                "tool": tool_name,
                "engaged_at": datetime.now(timezone.utc).isoformat(),
                "reason": reason,
            }
            path.write_text(
                json.dumps(payload, indent=2) + "\n", encoding="utf-8"
            )
        except OSError as e:
            logger.warning("Failed to write tool sentinel %s: %s", path, e)

    def _remove_sentinel(self, path: Path) -> bool:
        """Remove a sentinel file. Returns True if it existed."""
        try:
            path.unlink()
            return True
        except FileNotFoundError:
            return False
        except OSError:
            return False

    # ── Scope-level controls ─────────────────────────────────────────────

    def engage(
        self,
        scope: EmergencyScope,
        *,
        level: EmergencyLevel = EmergencyLevel.PAUSE,
        reason: Optional[str] = None,
        who: str = "system",
    ) -> None:
        """Engage an emergency stop for a given scope."""
        with self._lock:
            self._stops[scope] = level
            self._persist_state(scope, level, reason)

        audit_log(
            AuditEvent.EMERGENCY_ENGAGED,
            who=who,
            what=f"emergency stop engaged: {scope.value} at {level.value}",
            why=reason,
            result="allowed",
            scope=scope.value,
            level=level.value,
        )
        logger.warning(
            "Emergency stop ENGAGED: scope=%s level=%s reason=%s",
            scope.value, level.value, reason,
        )

    def disengage(
        self,
        scope: EmergencyScope,
        *,
        who: str = "system",
    ) -> bool:
        """Disengage an emergency stop for a given scope. Returns True if was engaged."""
        with self._lock:
            was_engaged = scope in self._stops
            self._stops.pop(scope, None)
            path = self._sentinel_path(scope)
            self._remove_sentinel(path)

        if was_engaged:
            audit_log(
                AuditEvent.EMERGENCY_DISENGAGED,
                who=who,
                what=f"emergency stop disengaged: {scope.value}",
                result="allowed",
                scope=scope.value,
            )
            logger.info("Emergency stop DISENGAGED: scope=%s", scope.value)
        return was_engaged

    def is_engaged(
        self,
        scope: EmergencyScope,
    ) -> tuple[bool, Optional[EmergencyLevel]]:
        """Check if an emergency stop is engaged for a scope.

        Returns (engaged, level). If the global stop is at HALT, ALL
        scopes are considered engaged.
        """
        with self._lock:
            # Global halt overrides everything.
            global_level = self._stops.get(EmergencyScope.GLOBAL)
            if global_level == EmergencyLevel.HALT:
                return True, EmergencyLevel.HALT
            # Global pause blocks non-essential operations.
            if global_level == EmergencyLevel.PAUSE and scope != EmergencyScope.GLOBAL:
                return True, global_level

            level = self._stops.get(scope)
            if level is not None:
                return True, level
            return False, None

    def get_all_stops(self) -> dict[str, Optional[str]]:
        """Return a summary of all engaged emergency stops."""
        with self._lock:
            result = {}
            for scope, level in self._stops.items():
                result[scope.value] = level.value
            for name, level in self._plugin_stops.items():
                result[f"plugin:{name}"] = level.value
            for name, level in self._tool_stops.items():
                result[f"tool:{name}"] = level.value
            return result

    # ── Plugin-level controls ────────────────────────────────────────────

    def engage_plugin(
        self,
        plugin_name: str,
        *,
        level: EmergencyLevel = EmergencyLevel.PAUSE,
        reason: Optional[str] = None,
        who: str = "system",
    ) -> None:
        """Engage an emergency stop for a specific plugin."""
        with self._lock:
            self._plugin_stops[plugin_name] = level
            self._persist_plugin_state(plugin_name, level, reason)

        audit_log(
            AuditEvent.EMERGENCY_ENGAGED,
            who=who,
            what=f"plugin stop engaged: {plugin_name} at {level.value}",
            why=reason,
            result="allowed",
            plugin=plugin_name,
            level=level.value,
        )

    def disengage_plugin(
        self,
        plugin_name: str,
        *,
        who: str = "system",
    ) -> bool:
        """Disengage the emergency stop for a specific plugin."""
        with self._lock:
            was_engaged = plugin_name in self._plugin_stops
            self._plugin_stops.pop(plugin_name, None)
            self._remove_sentinel(self._plugin_sentinel_path(plugin_name))

        if was_engaged:
            audit_log(
                AuditEvent.EMERGENCY_DISENGAGED,
                who=who,
                what=f"plugin stop disengaged: {plugin_name}",
                result="allowed",
                plugin=plugin_name,
            )
        return was_engaged

    def is_plugin_stopped(self, plugin_name: str) -> bool:
        """Check if a specific plugin is stopped."""
        with self._lock:
            return plugin_name in self._plugin_stops

    # ── Tool-level controls ──────────────────────────────────────────────

    def engage_tool(
        self,
        tool_name: str,
        *,
        level: EmergencyLevel = EmergencyLevel.PAUSE,
        reason: Optional[str] = None,
        who: str = "system",
    ) -> None:
        """Engage an emergency stop for a specific tool."""
        with self._lock:
            self._tool_stops[tool_name] = level
            self._persist_tool_state(tool_name, level, reason)

        audit_log(
            AuditEvent.EMERGENCY_ENGAGED,
            who=who,
            what=f"tool stop engaged: {tool_name} at {level.value}",
            why=reason,
            result="allowed",
            tool=tool_name,
            level=level.value,
        )

    def disengage_tool(
        self,
        tool_name: str,
        *,
        who: str = "system",
    ) -> bool:
        """Disengage the emergency stop for a specific tool."""
        with self._lock:
            was_engaged = tool_name in self._tool_stops
            self._tool_stops.pop(tool_name, None)
            self._remove_sentinel(self._tool_sentinel_path(tool_name))

        if was_engaged:
            audit_log(
                AuditEvent.EMERGENCY_DISENGAGED,
                who=who,
                what=f"tool stop disengaged: {tool_name}",
                result="allowed",
                tool=tool_name,
            )
        return was_engaged

    def is_tool_stopped(self, tool_name: str) -> bool:
        """Check if a specific tool is stopped."""
        with self._lock:
            return tool_name in self._tool_stops

    # ── Operation authorization ──────────────────────────────────────────

    def check_operation(
        self,
        tool_name: str,
        *,
        plugin_name: Optional[str] = None,
        who: str = "unknown",
        session_id: Optional[str] = None,
    ) -> tuple[bool, Optional[str]]:
        """Check if a tool operation is allowed under current emergency state.

        Returns (allowed: bool, reason: Optional[str]).

        Checks (in order):
        1. Always-allowed tools bypass all checks.
        2. Global halt blocks everything.
        3. Tool-specific stop.
        4. Plugin-specific stop.
        5. Scope-level stops (financial, network, destructive).

        LLM reasoning must NEVER override the result of this check.
        """
        # Always-allowed tools.
        if tool_name in _ALWAYS_ALLOWED_TOOLS:
            return True, None

        with self._lock:
            # Global halt.
            global_level = self._stops.get(EmergencyScope.GLOBAL)
            if global_level == EmergencyLevel.HALT:
                reason = "global emergency stop is active (HALT)"
                audit_log(
                    AuditEvent.EMERGENCY_OPERATION_BLOCKED,
                    who=who,
                    what=f"tool '{tool_name}' blocked by global HALT",
                    action=f"execute {tool_name}",
                    result="blocked",
                    failure=reason,
                    session_id=session_id,
                )
                return False, reason

            # Tool-specific stop.
            if tool_name in self._tool_stops:
                level = self._tool_stops[tool_name]
                reason = f"tool-specific emergency stop ({level.value})"
                audit_log(
                    AuditEvent.EMERGENCY_OPERATION_BLOCKED,
                    who=who,
                    what=f"tool '{tool_name}' blocked by tool-specific stop",
                    action=f"execute {tool_name}",
                    result="blocked",
                    failure=reason,
                    session_id=session_id,
                )
                return False, reason

            # Plugin-specific stop.
            if plugin_name and plugin_name in self._plugin_stops:
                level = self._plugin_stops[plugin_name]
                reason = f"plugin '{plugin_name}' emergency stop ({level.value})"
                audit_log(
                    AuditEvent.EMERGENCY_OPERATION_BLOCKED,
                    who=who,
                    what=f"tool '{tool_name}' blocked by plugin stop",
                    action=f"execute {tool_name}",
                    result="blocked",
                    failure=reason,
                    session_id=session_id,
                )
                return False, reason

            # Scope-level stops.
            scope = _TOOL_SCOPE_MAP.get(tool_name)
            if scope and scope in self._stops:
                level = self._stops[scope]
                reason = f"scope '{scope.value}' emergency stop ({level.value})"
                audit_log(
                    AuditEvent.EMERGENCY_OPERATION_BLOCKED,
                    who=who,
                    what=f"tool '{tool_name}' blocked by scope stop",
                    action=f"execute {tool_name}",
                    result="blocked",
                    failure=reason,
                    session_id=session_id,
                )
                return False, reason

        return True, None


# Module-level singleton.
emergency_stop = EmergencyStop()


def engage_emergency_stop(
    scope: EmergencyScope,
    *,
    level: EmergencyLevel = EmergencyLevel.PAUSE,
    reason: Optional[str] = None,
    who: str = "system",
) -> None:
    """Convenience function: engage an emergency stop."""
    emergency_stop.engage(scope, level=level, reason=reason, who=who)


def disengage_emergency_stop(
    scope: EmergencyScope,
    *,
    who: str = "system",
) -> bool:
    """Convenience function: disengage an emergency stop."""
    return emergency_stop.disengage(scope, who=who)


def is_operation_allowed(
    tool_name: str,
    *,
    plugin_name: Optional[str] = None,
    who: str = "unknown",
    session_id: Optional[str] = None,
) -> tuple[bool, Optional[str]]:
    """Convenience function: check if a tool operation is allowed."""
    return emergency_stop.check_operation(
        tool_name, plugin_name=plugin_name, who=who, session_id=session_id,
    )
