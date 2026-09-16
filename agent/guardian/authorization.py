"""Capability-based authorization for tools, agents, and plugins.

Every privileged operation must have deterministic authorization. This module
provides a capability registry and authorization manager that enforces:

- Tools declare required capabilities at registration time.
- Agents and plugins are granted explicit capability sets.
- Authorization checks are deterministic (no LLM in the loop).
- Deny is absolute — a capability denial cannot be overridden by a
  higher-level grant (deny-escalation protection).
- The ``hardline`` set is unconditionally denied regardless of capabilities.

Integration with the tool dispatch pipeline:
    ``agent.guardian.authorization.check_authorization()`` should be called
    before ``handle_function_call()`` in ``model_tools.py``. Tools that
    fail the check return a structured error to the LLM.

The LLM reasoning must NEVER override authorization decisions made here.
"""
from __future__ import annotations

import enum
import logging
import threading
from dataclasses import dataclass, field
from typing import Optional, Set

from agent.guardian.audit import AuditEvent, audit_log

logger = logging.getLogger(__name__)


class IdentityType(enum.Enum):
    """Types of identities that can be authorized."""

    USER = "user"
    AGENT = "agent"
    PLUGIN = "plugin"
    SERVICE = "service"
    SYSTEM = "system"


class Capability(enum.Enum):
    """Granular capabilities that can be granted to identities.

    Tools declare which capabilities they require. Identities are granted
    specific capability sets. The authorization check verifies the identity
    holds ALL required capabilities for a given operation.
    """

    # File operations
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"

    # Terminal / execution
    TERMINAL_EXECUTE = "terminal_execute"
    CODE_EXECUTE = "code_execute"

    # Network
    NETWORK_ACCESS = "network_access"
    WEB_SEARCH = "web_search"
    WEB_EXTRACT = "web_extract"
    BROWSER = "browser"

    # Messaging
    SEND_MESSAGE = "send_message"
    READ_MESSAGES = "read_messages"

    # Scheduling
    CRON_SCHEDULE = "cron_schedule"
    DELEGATE_TASK = "delegate_task"

    # Memory / knowledge
    MEMORY_READ = "memory_read"
    MEMORY_WRITE = "memory_write"
    SESSION_READ = "session_read"

    # Financial
    FINANCIAL_READ = "financial_read"
    FINANCIAL_TRADE = "financial_trade"
    FINANCIAL_EXECUTE = "financial_execute"

    # Destructive
    DESTRUCTIVE_ACTION = "destructive_action"

    # Administrative
    MANAGE_PLUGINS = "manage_plugins"
    MANAGE_AGENTS = "manage_agents"
    MANAGE_CONFIG = "manage_config"
    MANAGE_CREDENTIALS = "manage_credentials"

    # Emergency
    EMERGENCY_STOP = "emergency_stop"
    EMERGENCY_OVERRIDE = "emergency_override"


# Tools that require specific capabilities. Maps tool name -> required
# capabilities. A tool not in this map requires NO capabilities (open access).
# When adding new tools, register their capability requirements here.
TOOL_CAPABILITIES: dict[str, set[Capability]] = {
    # File tools
    "read_file": {Capability.FILE_READ},
    "write_file": {Capability.FILE_WRITE},
    "patch": {Capability.FILE_WRITE},
    "search_files": {Capability.FILE_READ},

    # Terminal
    "terminal": {Capability.TERMINAL_EXECUTE},
    "execute_code": {Capability.CODE_EXECUTE},

    # Network
    "web_search": {Capability.WEB_SEARCH},
    "web_extract": {Capability.WEB_EXTRACT},
    "browser_navigate": {Capability.BROWSER},
    "browser_click": {Capability.BROWSER},
    "browser_type": {Capability.BROWSER},

    # Messaging
    "send_message": {Capability.SEND_MESSAGE},

    # Scheduling
    "cronjob": {Capability.CRON_SCHEDULE},
    "delegate_task": {Capability.DELEGATE_TASK},

    # Memory
    "memory": {Capability.MEMORY_WRITE},
    "session_search": {Capability.SESSION_READ},

    # Financial
    "pionex_execute": {Capability.FINANCIAL_TRADE},
    "pionex_status": {Capability.FINANCIAL_READ},
    "pionex_positions": {Capability.FINANCIAL_READ},
    "bond_revenue": {Capability.FINANCIAL_EXECUTE},
    "media_farm": {Capability.FINANCIAL_EXECUTE},
    "crypto_opportunity_execute": {Capability.FINANCIAL_TRADE, Capability.FINANCIAL_EXECUTE},
    "crypto_opportunity_participate": {Capability.FINANCIAL_TRADE, Capability.FINANCIAL_EXECUTE},

    # Administrative
    "skill_manage": {Capability.MANAGE_PLUGINS},
    "config_manage": {Capability.MANAGE_CONFIG},
}

# Default capabilities for each identity type. More restrictive defaults
# for agents and plugins than for users.
DEFAULT_CAPABILITIES: dict[IdentityType, set[Capability]] = {
    IdentityType.USER: {
        Capability.FILE_READ,
        Capability.FILE_WRITE,
        Capability.TERMINAL_EXECUTE,
        Capability.CODE_EXECUTE,
        Capability.NETWORK_ACCESS,
        Capability.WEB_SEARCH,
        Capability.WEB_EXTRACT,
        Capability.BROWSER,
        Capability.SEND_MESSAGE,
        Capability.READ_MESSAGES,
        Capability.CRON_SCHEDULE,
        Capability.DELEGATE_TASK,
        Capability.MEMORY_READ,
        Capability.MEMORY_WRITE,
        Capability.SESSION_READ,
        Capability.FINANCIAL_READ,
        Capability.FINANCIAL_EXECUTE,
        Capability.EMERGENCY_STOP,
        Capability.MANAGE_PLUGINS,
        Capability.MANAGE_AGENTS,
        Capability.MANAGE_CONFIG,
    },
    IdentityType.AGENT: {
        Capability.FILE_READ,
        Capability.FILE_WRITE,
        Capability.TERMINAL_EXECUTE,
        Capability.CODE_EXECUTE,
        Capability.NETWORK_ACCESS,
        Capability.WEB_SEARCH,
        Capability.WEB_EXTRACT,
        Capability.BROWSER,
        Capability.SEND_MESSAGE,
        Capability.READ_MESSAGES,
        Capability.MEMORY_READ,
        Capability.MEMORY_WRITE,
        Capability.SESSION_READ,
    },
    IdentityType.PLUGIN: {
        Capability.FILE_READ,
        Capability.NETWORK_ACCESS,
    },
    IdentityType.SERVICE: {
        Capability.FILE_READ,
        Capability.NETWORK_ACCESS,
    },
    IdentityType.SYSTEM: {
        cap for cap in Capability  # System gets everything
    },
}


@dataclass
class Identity:
    """An authenticated identity with a capability set."""

    id: str
    type: IdentityType
    capabilities: set[Capability] = field(default_factory=set)
    denied: set[Capability] = field(default_factory=set)
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Initialize with defaults for the identity type if not provided.
        if not self.capabilities:
            self.capabilities = set(DEFAULT_CAPABILITIES.get(self.type, set()))


class AuthorizationManager:
    """Deterministic capability-based authorization for all privileged ops.

    Thread-safe. deny is absolute — an explicit deny cannot be overridden
    by any grant. The ``hardline`` set is unconditionally denied.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._identities: dict[str, Identity] = {}
        # Capabilities that are ALWAYS denied, regardless of grants.
        # These protect destructive operations that must never be automated.
        self._hardline_denied: set[Capability] = {
            Capability.EMERGENCY_OVERRIDE,
        }
        # Per-tool custom capability requirements (extends TOOL_CAPABILITIES).
        self._tool_overrides: dict[str, set[Capability]] = {}

    def register_identity(self, identity: Identity) -> None:
        """Register or update an identity's capabilities."""
        with self._lock:
            self._identities[identity.id] = identity

    def unregister_identity(self, identity_id: str) -> bool:
        """Remove an identity. Returns True if it existed."""
        with self._lock:
            return self._identities.pop(identity_id, None) is not None

    def get_identity(self, identity_id: str) -> Optional[Identity]:
        """Get an identity by ID."""
        with self._lock:
            return self._identities.get(identity_id)

    def grant_capability(
        self,
        identity_id: str,
        capability: Capability,
        *,
        reason: Optional[str] = None,
    ) -> bool:
        """Grant a capability to an identity. Returns True on success.

        Refuses to grant hardline-denied capabilities.
        Refuses to override explicit denials — an explicit deny is absolute
        and can only be cleared via ``clear_deny()``.
        """
        if capability in self._hardline_denied:
            logger.warning(
                "Cannot grant hardline-denied capability %s to %s",
                capability.value, identity_id,
            )
            return False
        with self._lock:
            identity = self._identities.get(identity_id)
            if identity is None:
                return False
            # Explicit deny is absolute — grant cannot override it.
            if capability in identity.denied:
                logger.warning(
                    "Cannot grant %s to %s: explicitly denied",
                    capability.value, identity_id,
                )
                return False
            identity.capabilities.add(capability)
        audit_log(
            AuditEvent.CAPABILITY_GRANTED,
            who=identity_id,
            what=f"granted {capability.value}",
            why=reason,
            result="allowed",
            identity_type=identity.type.value,
        )
        return True

    def revoke_capability(
        self,
        identity_id: str,
        capability: Capability,
        *,
        reason: Optional[str] = None,
    ) -> bool:
        """Revoke a capability from an identity. Returns True on success."""
        with self._lock:
            identity = self._identities.get(identity_id)
            if identity is None:
                return False
            identity.capabilities.discard(capability)
        audit_log(
            AuditEvent.CAPABILITY_REVOKED,
            who=identity_id,
            what=f"revoked {capability.value}",
            why=reason,
            result="allowed",
            identity_type=identity.type.value if identity else "unknown",
        )
        return True

    def deny_capability(
        self,
        identity_id: str,
        capability: Capability,
        *,
        reason: Optional[str] = None,
    ) -> bool:
        """Explicitly deny a capability (absolute — cannot be overridden by grant).

        Returns True on success. Only ``clear_deny()`` can remove an
        explicit deny.
        """
        with self._lock:
            identity = self._identities.get(identity_id)
            if identity is None:
                return False
            identity.capabilities.discard(capability)
            identity.denied.add(capability)
        audit_log(
            AuditEvent.AUTHZ_DENIED,
            who=identity_id,
            what=f"denied {capability.value}",
            why=reason,
            result="denied",
            identity_type=identity.type.value if identity else "unknown",
        )
        return True

    def set_tool_capabilities(
        self,
        tool_name: str,
        capabilities: set[Capability],
    ) -> None:
        """Override the default capability requirements for a tool."""
        with self._lock:
            self._tool_overrides[tool_name] = set(capabilities)

    def get_required_capabilities(self, tool_name: str) -> set[Capability]:
        """Get the capabilities required to use a tool."""
        with self._lock:
            if tool_name in self._tool_overrides:
                return set(self._tool_overrides[tool_name])
        return set(TOOL_CAPABILITIES.get(tool_name, set()))

    def clear_deny(
        self,
        identity_id: str,
        capability: Capability,
    ) -> bool:
        """Remove an explicit deny (the ONLY way to undo a deny).

        Returns True on success.
        """
        with self._lock:
            identity = self._identities.get(identity_id)
            if identity is None:
                return False
            identity.denied.discard(capability)
        return True

    def check_authorization(
        self,
        identity_id: str,
        tool_name: str,
        *,
        session_id: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> tuple[bool, Optional[str]]:
        """Deterministic authorization check for a tool invocation.

        Returns (allowed: bool, failure_reason: Optional[str]).

        This is the core authorization gate. It must be called before
        every tool dispatch. LLM reasoning must NEVER bypass this check.

        Checks (in order):
        1. Identity must be registered.
        2. Identity must not be explicitly denied the required capabilities.
        3. Identity must hold ALL required capabilities.
        4. Hardline-denied capabilities are always blocked.
        """
        required = self.get_required_capabilities(tool_name)
        if not required:
            # Tool requires no capabilities — always allowed.
            return True, None

        with self._lock:
            identity = self._identities.get(identity_id)

        if identity is None:
            failure = f"unknown identity: {identity_id}"
            audit_log(
                AuditEvent.AUTHZ_DENIED,
                who=identity_id,
                what=f"tool '{tool_name}' requires {required}",
                why=reason,
                action=f"execute {tool_name}",
                result="denied",
                failure=failure,
                session_id=session_id,
            )
            return False, failure

        # Check hardline denials (always block).
        hardline_hit = required & self._hardline_denied
        if hardline_hit:
            failure = (
                f"hardline-denied capabilities: "
                f"{[c.value for c in hardline_hit]}"
            )
            audit_log(
                AuditEvent.HARDLINE_BLOCKED,
                who=identity_id,
                what=f"tool '{tool_name}' requires hardline-denied capabilities",
                why=reason,
                action=f"execute {tool_name}",
                result="blocked",
                failure=failure,
                session_id=session_id,
                identity_type=identity.type.value,
            )
            return False, failure

        # Check explicit denials (absolute — cannot be overridden).
        explicit_denials = required & identity.denied
        if explicit_denials:
            failure = (
                f"explicitly denied capabilities: "
                f"{[c.value for c in explicit_denials]}"
            )
            audit_log(
                AuditEvent.AUTHZ_DENIED,
                who=identity_id,
                what=f"tool '{tool_name}' requires denied capabilities",
                why=reason,
                action=f"execute {tool_name}",
                result="denied",
                failure=failure,
                session_id=session_id,
                identity_type=identity.type.value,
            )
            return False, failure

        # Check granted capabilities (must hold ALL required).
        missing = required - identity.capabilities
        if missing:
            failure = (
                f"missing capabilities: {[c.value for c in missing]}"
            )
            audit_log(
                AuditEvent.AUTHZ_DENIED,
                who=identity_id,
                what=f"tool '{tool_name}' requires missing capabilities",
                why=reason,
                action=f"execute {tool_name}",
                result="denied",
                failure=failure,
                session_id=session_id,
                identity_type=identity.type.value,
            )
            return False, failure

        # All checks passed.
        audit_log(
            AuditEvent.AUTHZ_GRANTED,
            who=identity_id,
            what=f"tool '{tool_name}' authorized",
            why=reason,
            action=f"execute {tool_name}",
            result="allowed",
            session_id=session_id,
            identity_type=identity.type.value,
        )
        return True, None


# Module-level singleton.
authorization_manager = AuthorizationManager()


def check_authorization(
    identity_id: str,
    tool_name: str,
    *,
    session_id: Optional[str] = None,
    reason: Optional[str] = None,
) -> tuple[bool, Optional[str]]:
    """Convenience function: check if an identity is authorized to use a tool."""
    return authorization_manager.check_authorization(
        identity_id, tool_name, session_id=session_id, reason=reason,
    )


def grant_capability(
    identity_id: str,
    capability: Capability,
    *,
    reason: Optional[str] = None,
) -> bool:
    """Convenience function: grant a capability to an identity."""
    return authorization_manager.grant_capability(
        identity_id, capability, reason=reason,
    )


def revoke_capability(
    identity_id: str,
    capability: Capability,
    *,
    reason: Optional[str] = None,
) -> bool:
    """Convenience function: revoke a capability from an identity."""
    return authorization_manager.revoke_capability(
        identity_id, capability, reason=reason,
    )
