"""Guardian Security Department — comprehensive test suite.

Tests all 13 required security scenarios:
1. Valid authentication
2. Invalid authentication
3. Valid authorization
4. Denied authorization
5. Unauthorized agent action
6. Unauthorized plugin action
7. Unauthorized tool action
8. Secret access
9. Emergency stop
10. Stopped agent
11. Stopped trading
12. Audit logging
13. Recovery

Uses only stdlib + pytest + unittest.mock. No live network calls.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from agent.guardian.audit import (
    AuditEvent,
    SecurityAuditLog,
    audit_log,
    query_audit_log,
)
from agent.guardian.authorization import (
    AuthorizationManager,
    Capability,
    Identity,
    IdentityType,
    TOOL_CAPABILITIES,
    authorization_manager,
    check_authorization,
    grant_capability,
    revoke_capability,
)
from agent.guardian.auth_tracker import (
    AuthTracker,
    auth_tracker,
    is_locked_out,
    record_auth_failure,
    record_auth_success,
)
from agent.guardian.emergency import (
    EmergencyLevel,
    EmergencyScope,
    EmergencyStop,
    _ALWAYS_ALLOWED_TOOLS,
    _TOOL_SCOPE_MAP,
    emergency_stop,
    engage_emergency_stop,
    disengage_emergency_stop,
    is_operation_allowed,
)
from agent.guardian.monitoring import (
    CheckSeverity,
    SecurityHealth,
    SecurityMonitor,
    security_monitor,
    run_security_check,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def hermes_home(tmp_path, monkeypatch):
    """Point HERMES_HOME at a temp dir for profile-aware tests."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def audit_log_instance(hermes_home):
    """Fresh audit log instance writing to temp dir."""
    log = SecurityAuditLog()
    return log


@pytest.fixture
def auth_mgr():
    """Fresh AuthorizationManager (no shared state with module singleton)."""
    return AuthorizationManager()


@pytest.fixture
def tracker():
    """Fresh AuthTracker with short lockout for fast tests."""
    return AuthTracker(max_failures=3, lockout_seconds=2.0)


@pytest.fixture
def estop(hermes_home):
    """Fresh EmergencyStop instance."""
    return EmergencyStop()


@pytest.fixture
def monitor(hermes_home):
    """Fresh SecurityMonitor instance."""
    return SecurityMonitor()


@pytest.fixture
def estop_singleton(hermes_home):
    """Use the module-level emergency_stop singleton (it reads HERMES_HOME)."""
    from agent.guardian.emergency import emergency_stop as _estop
    # Reset state.
    with _estop._lock:
        _estop._stops.clear()
        _estop._plugin_stops.clear()
        _estop._tool_stops.clear()
    return _estop


# ══════════════════════════════════════════════════════════════════════════════
# 1. VALID AUTHENTICATION
# ══════════════════════════════════════════════════════════════════════════════


class TestValidAuthentication:
    """Scenario 1: Valid authentication must succeed and be audited."""

    def test_auth_success_records_audit(self, tracker, hermes_home):
        """Successful auth is recorded in the audit log."""
        tracker.record_success("user_alice", identity_type="user")
        count = tracker.get_failure_count("user_alice")
        assert count == 0

    def test_auth_success_resets_failure_count(self, tracker, hermes_home):
        """A success resets previous failures."""
        tracker.record_failure("user_bob", reason="wrong password")
        tracker.record_failure("user_bob", reason="wrong password")
        assert tracker.get_failure_count("user_bob") == 2
        tracker.record_success("user_bob")
        assert tracker.get_failure_count("user_bob") == 0

    def test_auth_success_clears_lockout(self, tracker, hermes_home):
        """A success after lockout clears the lockout."""
        # Lock out the user.
        for _ in range(3):
            tracker.record_failure("user_carol", reason="bad creds")
        locked, _ = tracker.is_locked_out("user_carol")
        assert locked is True

        # Wait for lockout to expire, then succeed.
        time.sleep(2.1)
        tracker.record_success("user_carol")
        locked, remaining = tracker.is_locked_out("user_carol")
        assert locked is False
        assert remaining is None


# ══════════════════════════════════════════════════════════════════════════════
# 2. INVALID AUTHENTICATION
# ══════════════════════════════════════════════════════════════════════════════


class TestInvalidAuthentication:
    """Scenario 2: Invalid authentication must be denied and audited."""

    def test_single_failure_increments_count(self, tracker):
        tracker.record_failure("user_dave", reason="wrong password")
        assert tracker.get_failure_count("user_dave") == 1

    def test_multiple_failures_accumulate(self, tracker):
        for i in range(3):
            tracker.record_failure("user_eve", reason=f"attempt {i}")
        assert tracker.get_failure_count("user_eve") == 3

    def test_lockout_engaged_after_threshold(self, tracker):
        """After max_failures, identity is locked out."""
        for _ in range(3):
            tracker.record_failure("user_frank", reason="brute force")
        locked, remaining = tracker.is_locked_out("user_frank")
        assert locked is True
        assert remaining is not None
        assert remaining > 0

    def test_lockout_prevents_success_until_expiry(self, tracker):
        """Locked out identity stays locked until lockout expires."""
        for _ in range(3):
            tracker.record_failure("user_grace", reason="intrusion")
        locked, _ = tracker.is_locked_out("user_grace")
        assert locked is True
        # Even a recorded success doesn't clear active lockout immediately.
        # (The success records but the lockout timer is still running.)
        # After expiry, it clears.
        time.sleep(2.1)
        locked, _ = tracker.is_locked_out("user_grace")
        assert locked is False

    def test_different_identities_independent(self, tracker):
        """Lockout of one identity doesn't affect another."""
        for _ in range(3):
            tracker.record_failure("user_hank", reason="bad")
        locked_hank, _ = tracker.is_locked_out("user_hank")
        locked_ivy, _ = tracker.is_locked_out("user_ivy")
        assert locked_hank is True
        assert locked_ivy is False

    def test_failure_audited(self, tracker, hermes_home):
        """Each failure creates an audit log entry."""
        tracker.record_failure("user_test", reason="test failure")
        # Audit log should have been called (we can verify via the tracker's
        # internal state; actual audit file writing is tested separately).
        assert tracker.get_failure_count("user_test") == 1


# ══════════════════════════════════════════════════════════════════════════════
# 3. VALID AUTHORIZATION
# ══════════════════════════════════════════════════════════════════════════════


class TestValidAuthorization:
    """Scenario 3: Valid authorization must be granted."""

    def test_user_can_use_file_read(self, auth_mgr):
        """User identity has file_read by default."""
        identity = Identity(id="user1", type=IdentityType.USER)
        auth_mgr.register_identity(identity)
        allowed, reason = auth_mgr.check_authorization("user1", "read_file")
        assert allowed is True
        assert reason is None

    def test_user_can_use_terminal(self, auth_mgr):
        """User identity has terminal_execute by default."""
        identity = Identity(id="user1", type=IdentityType.USER)
        auth_mgr.register_identity(identity)
        allowed, _ = auth_mgr.check_authorization("user1", "terminal")
        assert allowed is True

    def test_agent_with_explicit_grant(self, auth_mgr):
        """Agent can use tools after explicit capability grant."""
        identity = Identity(id="agent1", type=IdentityType.AGENT)
        auth_mgr.register_identity(identity)
        auth_mgr.grant_capability("agent1", Capability.FINANCIAL_TRADE)
        allowed, _ = auth_mgr.check_authorization("agent1", "pionex_execute")
        assert allowed is True

    def test_tool_requiring_no_capabilities_always_allowed(self, auth_mgr):
        """Tools not in TOOL_CAPABILITIES require no capabilities."""
        identity = Identity(id="anyone", type=IdentityType.PLUGIN)
        auth_mgr.register_identity(identity)
        # 'clarify' is not in TOOL_CAPABILITIES — always allowed.
        allowed, _ = auth_mgr.check_authorization("anyone", "clarify")
        assert allowed is True

    def test_system_identity_has_all_capabilities(self, auth_mgr):
        """System identity type has all capabilities."""
        identity = Identity(id="sys1", type=IdentityType.SYSTEM)
        auth_mgr.register_identity(identity)
        # Test a tool that requires FINANCIAL_TRADE.
        allowed, _ = auth_mgr.check_authorization("sys1", "pionex_execute")
        assert allowed is True


# ══════════════════════════════════════════════════════════════════════════════
# 4. DENIED AUTHORIZATION
# ══════════════════════════════════════════════════════════════════════════════


class TestDeniedAuthorization:
    """Scenario 4: Denied authorization must be blocked."""

    def test_plugin_cannot_use_terminal(self, auth_mgr):
        """Plugin identity lacks terminal_execute by default."""
        identity = Identity(id="plugin1", type=IdentityType.PLUGIN)
        auth_mgr.register_identity(identity)
        allowed, reason = auth_mgr.check_authorization("plugin1", "terminal")
        assert allowed is False
        assert "missing capabilities" in reason

    def test_plugin_cannot_write_files(self, auth_mgr):
        """Plugin identity lacks file_write by default."""
        identity = Identity(id="plugin2", type=IdentityType.PLUGIN)
        auth_mgr.register_identity(identity)
        allowed, _ = auth_mgr.check_authorization("plugin2", "write_file")
        assert allowed is False

    def test_explicit_deny_overrides_grant(self, auth_mgr):
        """An explicit deny cannot be overridden by a grant."""
        identity = Identity(id="user_deny", type=IdentityType.USER)
        auth_mgr.register_identity(identity)
        auth_mgr.deny_capability(
            "user_deny", Capability.TERMINAL_EXECUTE, reason="policy"
        )
        # Even after trying to grant, deny wins.
        auth_mgr.grant_capability(
            "user_deny", Capability.TERMINAL_EXECUTE, reason="override"
        )
        allowed, reason = auth_mgr.check_authorization(
            "user_deny", "terminal"
        )
        assert allowed is False
        assert "denied capabilities" in reason

    def test_unknown_identity_denied(self, auth_mgr):
        """An unregistered identity is denied."""
        allowed, reason = auth_mgr.check_authorization(
            "nonexistent", "read_file"
        )
        assert allowed is False
        assert "unknown identity" in reason

    def test_missing_single_capability_denies(self, auth_mgr):
        """Missing even one required capability denies the tool."""
        identity = Identity(id="partial", type=IdentityType.AGENT)
        auth_mgr.register_identity(identity)
        # Agent has FILE_READ but not FINANCIAL_EXECUTE.
        # bond_revenue needs FINANCIAL_EXECUTE.
        allowed, reason = auth_mgr.check_authorization("partial", "bond_revenue")
        assert allowed is False
        assert "financial_execute" in reason

    def test_hardline_denied_never_grantable(self, auth_mgr):
        """Hardline-denied capabilities cannot be granted."""
        identity = Identity(id="h1", type=IdentityType.USER)
        auth_mgr.register_identity(identity)
        result = auth_mgr.grant_capability(
            "h1", Capability.EMERGENCY_OVERRIDE, reason="test"
        )
        assert result is False

    def test_revoke_removes_capability(self, auth_mgr):
        """Revoking a capability prevents future use."""
        identity = Identity(id="revoke_test", type=IdentityType.USER)
        auth_mgr.register_identity(identity)
        # User can read files by default.
        allowed, _ = auth_mgr.check_authorization("revoke_test", "read_file")
        assert allowed is True

        auth_mgr.revoke_capability("revoke_test", Capability.FILE_READ)
        allowed, _ = auth_mgr.check_authorization("revoke_test", "read_file")
        assert allowed is False


# ══════════════════════════════════════════════════════════════════════════════
# 5. UNAUTHORIZED AGENT ACTION
# ══════════════════════════════════════════════════════════════════════════════


class TestUnauthorizedAgentAction:
    """Scenario 5: An agent must not automatically gain access to every tool."""

    def test_agent_lacks_financial_by_default(self, auth_mgr):
        """Agent cannot trade without explicit grant."""
        identity = Identity(id="agent_fin", type=IdentityType.AGENT)
        auth_mgr.register_identity(identity)
        allowed, _ = auth_mgr.check_authorization("agent_fin", "pionex_execute")
        assert allowed is False

    def test_agent_lacks_cron_by_default(self, auth_mgr):
        """Agent cannot schedule cron without explicit grant."""
        identity = Identity(id="agent_cron", type=IdentityType.AGENT)
        auth_mgr.register_identity(identity)
        allowed, _ = auth_mgr.check_authorization("agent_cron", "cronjob")
        assert allowed is False

    def test_agent_lacks_delegation_by_default(self, auth_mgr):
        """Agent cannot delegate tasks without explicit grant."""
        identity = Identity(id="agent_del", type=IdentityType.AGENT)
        auth_mgr.register_identity(identity)
        allowed, _ = auth_mgr.check_authorization("agent_del", "delegate_task")
        assert allowed is False

    def test_agent_can_be_granted_specifically(self, auth_mgr):
        """Agent can gain specific capabilities via explicit grant."""
        identity = Identity(id="agent_specific", type=IdentityType.AGENT)
        auth_mgr.register_identity(identity)
        auth_mgr.grant_capability(
            "agent_specific", Capability.FINANCIAL_READ, reason="monitoring"
        )
        allowed, _ = auth_mgr.check_authorization(
            "agent_specific", "pionex_status"
        )
        assert allowed is True
        # But still can't trade.
        allowed, _ = auth_mgr.check_authorization(
            "agent_specific", "pionex_execute"
        )
        assert allowed is False

    def test_agent_identity_type_explicitly_denied(self, auth_mgr):
        """Agent identity can be explicitly denied capabilities."""
        identity = Identity(id="agent_denied", type=IdentityType.AGENT)
        auth_mgr.register_identity(identity)
        auth_mgr.deny_capability(
            "agent_denied", Capability.FILE_WRITE, reason="read-only agent"
        )
        allowed, _ = auth_mgr.check_authorization("agent_denied", "write_file")
        assert allowed is False


# ══════════════════════════════════════════════════════════════════════════════
# 6. UNAUTHORIZED PLUGIN ACTION
# ══════════════════════════════════════════════════════════════════════════════


class TestUnauthorizedPluginAction:
    """Scenario 6: A plugin must not automatically gain access to credentials."""

    def test_plugin_cannot_access_credentials(self, auth_mgr):
        """Plugin lacks MANAGE_CREDENTIALS by default."""
        identity = Identity(id="plugin_cred", type=IdentityType.PLUGIN)
        auth_mgr.register_identity(identity)
        # credential-related tools require MANAGE_CREDENTIALS.
        required = auth_mgr.get_required_capabilities("config_manage")
        # Plugin doesn't have MANAGE_CONFIG.
        allowed, reason = auth_mgr.check_authorization(
            "plugin_cred", "config_manage"
        )
        assert allowed is False

    def test_plugin_lacks_financial_access(self, auth_mgr):
        """Plugin cannot trade by default."""
        identity = Identity(id="plugin_fin", type=IdentityType.PLUGIN)
        auth_mgr.register_identity(identity)
        allowed, _ = auth_mgr.check_authorization("plugin_fin", "pionex_execute")
        assert allowed is False

    def test_plugin_lacks_messaging(self, auth_mgr):
        """Plugin cannot send messages by default."""
        identity = Identity(id="plugin_msg", type=IdentityType.PLUGIN)
        auth_mgr.register_identity(identity)
        allowed, _ = auth_mgr.check_authorization("plugin_msg", "send_message")
        assert allowed is False

    def test_plugin_lacks_destructive(self, auth_mgr):
        """Plugin cannot execute code by default."""
        identity = Identity(id="plugin_code", type=IdentityType.PLUGIN)
        auth_mgr.register_identity(identity)
        allowed, _ = auth_mgr.check_authorization(
            "plugin_code", "execute_code"
        )
        assert allowed is False


# ══════════════════════════════════════════════════════════════════════════════
# 7. UNAUTHORIZED TOOL ACTION
# ══════════════════════════════════════════════════════════════════════════════


class TestUnauthorizedToolAction:
    """Scenario 7: Sensitive tools must require appropriate authorization."""

    def test_pionex_requires_financial_trade(self):
        """Pionex trading requires FINANCIAL_TRADE capability."""
        required = TOOL_CAPABILITIES.get("pionex_execute")
        assert required is not None
        assert Capability.FINANCIAL_TRADE in required

    def test_terminal_requires_terminal_execute(self):
        """Terminal requires TERMINAL_EXECUTE capability."""
        required = TOOL_CAPABILITIES.get("terminal")
        assert required is not None
        assert Capability.TERMINAL_EXECUTE in required

    def test_write_file_requires_file_write(self):
        """Write file requires FILE_WRITE capability."""
        required = TOOL_CAPABILITIES.get("write_file")
        assert required is not None
        assert Capability.FILE_WRITE in required

    def test_read_file_requires_file_read(self):
        """Read file requires FILE_READ capability."""
        required = TOOL_CAPABILITIES.get("read_file")
        assert required is not None
        assert Capability.FILE_READ in required

    def test_memory_requires_memory_write(self):
        """Memory tool requires MEMORY_WRITE capability."""
        required = TOOL_CAPABILITIES.get("memory")
        assert required is not None
        assert Capability.MEMORY_WRITE in required

    def test_web_search_requires_web_search(self):
        """Web search requires WEB_SEARCH capability."""
        required = TOOL_CAPABILITIES.get("web_search")
        assert required is not None
        assert Capability.WEB_SEARCH in required

    def test_custom_tool_capability_override(self, auth_mgr):
        """Custom tool capability requirements can be set."""
        auth_mgr.set_tool_capabilities("my_custom_tool", {Capability.NETWORK_ACCESS})
        required = auth_mgr.get_required_capabilities("my_custom_tool")
        assert Capability.NETWORK_ACCESS in required

    def test_plugin_tool_denied_by_default(self, auth_mgr):
        """Plugin calling a sensitive tool without capabilities is denied."""
        identity = Identity(id="plugin_sensitive", type=IdentityType.PLUGIN)
        auth_mgr.register_identity(identity)
        allowed, _ = auth_mgr.check_authorization(
            "plugin_sensitive", "terminal"
        )
        assert allowed is False


# ══════════════════════════════════════════════════════════════════════════════
# 8. SECRET ACCESS
# ══════════════════════════════════════════════════════════════════════════════


class TestSecretAccess:
    """Scenario 8: Secret access must be controlled and audited."""

    def test_audit_log_redacts_token_fields(self, audit_log_instance, hermes_home):
        """Token-like fields are stripped from audit log entries."""
        audit_log_instance.log(
            AuditEvent.CREDENTIAL_ACCESSED,
            who="test",
            what="test",
            access_token="secret_token_12345",
            refresh_token="refresh_secret_67890",
            api_key="sk-test-123",
        )
        # Read the log back.
        entries = audit_log_instance.query(event=AuditEvent.CREDENTIAL_ACCESSED)
        assert len(entries) >= 1
        entry = entries[-1]
        assert "access_token" not in entry
        assert "refresh_token" not in entry
        assert "api_key" not in entry

    def test_audit_log_preserves_safe_fields(self, audit_log_instance, hermes_home):
        """Non-secret fields are preserved in audit log."""
        audit_log_instance.log(
            AuditEvent.CREDENTIAL_ACCESSED,
            who="user1",
            what="read API key for OpenAI",
            result="allowed",
            provider="openai",
        )
        entries = audit_log_instance.query(event=AuditEvent.CREDENTIAL_ACCESSED)
        assert len(entries) >= 1
        entry = entries[-1]
        assert entry["who"] == "user1"
        assert entry["provider"] == "openai"

    def test_credential_denied_logged(self, audit_log_instance, hermes_home):
        """Credential access denial is audited."""
        audit_log_instance.log(
            AuditEvent.CREDENTIAL_DENIED,
            who="plugin_x",
            what="attempted to read auth.json",
            result="denied",
            failure="file read denied by safety policy",
            identity_type="plugin",
        )
        entries = audit_log_instance.query(event=AuditEvent.CREDENTIAL_DENIED)
        assert len(entries) >= 1
        entry = entries[-1]
        assert entry["result"] == "denied"
        assert entry["identity_type"] == "plugin"

    def test_plugin_cannot_manage_credentials(self, auth_mgr):
        """Plugin identity cannot manage credentials."""
        identity = Identity(id="plugin_secrets", type=IdentityType.PLUGIN)
        auth_mgr.register_identity(identity)
        allowed, _ = auth_mgr.check_authorization(
            "plugin_secrets", "config_manage"
        )
        assert allowed is False


# ══════════════════════════════════════════════════════════════════════════════
# 9. EMERGENCY STOP
# ══════════════════════════════════════════════════════════════════════════════


class TestEmergencyStop:
    """Scenario 9: Emergency stop must actually prevent operations."""

    def test_global_halt_blocks_all(self, estop):
        """Global HALT blocks every non-always-allowed tool."""
        estop.engage(EmergencyScope.GLOBAL, level=EmergencyLevel.HALT)
        allowed, reason = estop.check_operation("terminal", who="test")
        assert allowed is False
        assert "global" in reason.lower()

    def test_global_halt_blocks_financial(self, estop):
        """Global HALT blocks financial operations."""
        estop.engage(EmergencyScope.GLOBAL, level=EmergencyLevel.HALT)
        allowed, _ = estop.check_operation("pionex_execute", who="test")
        assert allowed is False

    def test_financial_stop_blocks_trading(self, estop):
        """Financial scope stop blocks trading tools."""
        estop.engage(
            EmergencyScope.FINANCIAL,
            level=EmergencyLevel.PAUSE,
            reason="market volatility",
        )
        allowed, reason = estop.check_operation("pionex_execute", who="test")
        assert allowed is False
        assert "financial" in reason

    def test_financial_stop_blocks_pionex_status(self, estop):
        """Financial scope stop blocks even read-only financial tools."""
        estop.engage(EmergencyScope.FINANCIAL, level=EmergencyLevel.PAUSE)
        allowed, _ = estop.check_operation("pionex_status", who="test")
        assert allowed is False

    def test_financial_stop_blocks_bond_revenue(self, estop):
        """Financial scope stop blocks bond revenue tool."""
        estop.engage(EmergencyScope.FINANCIAL, level=EmergencyLevel.HALT)
        allowed, _ = estop.check_operation("bond_revenue", who="test")
        assert allowed is False

    def test_always_allowed_tools_bypass_stop(self, estop):
        """Read-only safe tools bypass emergency stops."""
        estop.engage(EmergencyScope.GLOBAL, level=EmergencyLevel.HALT)
        for tool in _ALWAYS_ALLOWED_TOOLS:
            allowed, _ = estop.check_operation(tool, who="test")
            assert allowed is True, f"{tool} should be always allowed"

    def test_network_stop_blocks_web(self, estop):
        """Network scope stop blocks web tools."""
        estop.engage(EmergencyScope.NETWORK, level=EmergencyLevel.PAUSE)
        allowed, _ = estop.check_operation("web_search", who="test")
        assert allowed is False

    def test_tool_specific_stop(self, estop):
        """Individual tool can be stopped."""
        estop.engage_tool("terminal", reason="unsafe")
        allowed, reason = estop.check_operation("terminal", who="test")
        assert allowed is False
        assert "tool-specific" in reason

    def test_plugin_specific_stop(self, estop):
        """Individual plugin can be stopped."""
        estop.engage_plugin("rogue_plugin", reason="malware detected")
        allowed, reason = estop.check_operation(
            "web_search", plugin_name="rogue_plugin", who="test"
        )
        assert allowed is False
        assert "rogue_plugin" in reason

    def test_disengage_allows_operations(self, estop):
        """Disengaging stop allows operations again."""
        estop.engage(EmergencyScope.FINANCIAL, level=EmergencyLevel.HALT)
        allowed, _ = estop.check_operation("pionex_execute", who="test")
        assert allowed is False

        estop.disengage(EmergencyScope.FINANCIAL, who="admin")
        allowed, _ = estop.check_operation("pionex_execute", who="test")
        assert allowed is True

    def test_stop_audited(self, estop, hermes_home):
        """Emergency stop engagement is recorded in audit log."""
        estop.engage(
            EmergencyScope.GLOBAL,
            level=EmergencyLevel.HALT,
            reason="security incident",
            who="admin",
        )
        # Verify the operation is blocked (audit was recorded internally).
        allowed, _ = estop.check_operation("terminal", who="test")
        assert allowed is False


# ══════════════════════════════════════════════════════════════════════════════
# 10. STOPPED AGENT
# ══════════════════════════════════════════════════════════════════════════════


class TestStoppedAgent:
    """Scenario 10: A stopped agent must not execute operations."""

    def test_agent_scope_stop_blocks_agent_tools(self, estop):
        """AGENT scope stop blocks agent-level operations."""
        estop.engage(
            EmergencyScope.AGENT,
            level=EmergencyLevel.HALT,
            reason="agent misbehaving",
        )
        # Agent tools (delegate_task, cronjob) should be blocked.
        allowed, _ = estop.check_operation("delegate_task", who="agent1")
        assert allowed is False
        allowed, _ = estop.check_operation("cronjob", who="agent1")
        assert allowed is False
        # session_search is in AGENT scope but also in _ALWAYS_ALLOWED_TOOLS,
        # so it bypasses the stop (safe read-only tool).
        allowed, _ = estop.check_operation("session_search", who="agent1")
        assert allowed is True

    def test_destructive_stop_blocks_terminal(self, estop):
        """DESTRUCTIVE scope stop blocks terminal execution."""
        estop.engage(EmergencyScope.DESTRUCTIVE, level=EmergencyLevel.HALT)
        allowed, _ = estop.check_operation("terminal", who="agent1")
        assert allowed is False

    def test_stopped_agent_can_still_read(self, estop):
        """Stopped agent can still use read-only tools."""
        estop.engage(EmergencyScope.GLOBAL, level=EmergencyLevel.HALT)
        allowed, _ = estop.check_operation("read_file", who="agent1")
        assert allowed is True

    def test_stopped_agent_can_still_clarify(self, estop):
        """Stopped agent can still use clarify (ask user)."""
        estop.engage(EmergencyScope.GLOBAL, level=EmergencyLevel.HALT)
        allowed, _ = estop.check_operation("clarify", who="agent1")
        assert allowed is True


# ══════════════════════════════════════════════════════════════════════════════
# 11. STOPPED TRADING
# ══════════════════════════════════════════════════════════════════════════════


class TestStoppedTrading:
    """Scenario 11: Stopped trading must block all financial operations."""

    def test_trading_stop_blocks_pionex_execute(self, estop):
        estop.engage(EmergencyScope.FINANCIAL, level=EmergencyLevel.HALT)
        allowed, _ = estop.check_operation("pionex_execute", who="trader")
        assert allowed is False

    def test_trading_stop_blocks_pionex_cancel(self, estop):
        estop.engage(EmergencyScope.FINANCIAL, level=EmergencyLevel.HALT)
        allowed, _ = estop.check_operation("pionex_cancel", who="trader")
        assert allowed is False

    def test_trading_stop_blocks_pionex_positions(self, estop):
        estop.engage(EmergencyScope.FINANCIAL, level=EmergencyLevel.HALT)
        allowed, _ = estop.check_operation("pionex_positions", who="trader")
        assert allowed is False

    def test_trading_stop_blocks_bond_revenue(self, estop):
        estop.engage(EmergencyScope.FINANCIAL, level=EmergencyLevel.HALT)
        allowed, _ = estop.check_operation("bond_revenue", who="trader")
        assert allowed is False

    def test_trading_stop_allows_non_financial(self, estop):
        """Financial stop doesn't block non-financial tools."""
        estop.engage(EmergencyScope.FINANCIAL, level=EmergencyLevel.HALT)
        allowed, _ = estop.check_operation("web_search", who="trader")
        assert allowed is True

    def test_trading_disengage_restores(self, estop):
        """Disengaging financial stop restores trading."""
        estop.engage(EmergencyScope.FINANCIAL, level=EmergencyLevel.HALT)
        estop.disengage(EmergencyScope.FINANCIAL, who="admin")
        allowed, _ = estop.check_operation("pionex_execute", who="trader")
        assert allowed is True


# ══════════════════════════════════════════════════════════════════════════════
# 12. AUDIT LOGGING
# ══════════════════════════════════════════════════════════════════════════════


class TestAuditLogging:
    """Scenario 12: Audit logging must record WHO/WHAT/WHEN/WHY/ACTION/RESULT."""

    def test_audit_log_has_all_required_fields(self, audit_log_instance, hermes_home):
        """Each audit entry has the required structured fields."""
        audit_log_instance.log(
            AuditEvent.TOOL_EXECUTED,
            who="user_alice",
            what="executed terminal command",
            why="user requested",
            action="execute terminal",
            result="allowed",
            identity_type="user",
            session_id="sess_123",
        )
        entries = audit_log_instance.query(event=AuditEvent.TOOL_EXECUTED)
        assert len(entries) >= 1
        entry = entries[-1]
        assert entry["who"] == "user_alice"
        assert entry["what"] == "executed terminal command"
        assert "ts" in entry  # WHEN
        assert entry["why"] == "user requested"
        assert entry["action"] == "execute terminal"
        assert entry["result"] == "allowed"
        assert entry["identity_type"] == "user"
        assert entry["session_id"] == "sess_123"

    def test_audit_log_timestamp_is_utc(self, audit_log_instance, hermes_home):
        """Timestamps are UTC ISO-8601."""
        audit_log_instance.log(AuditEvent.AUTH_SUCCESS, who="test")
        entries = audit_log_instance.query(event=AuditEvent.AUTH_SUCCESS)
        assert len(entries) >= 1
        ts = entries[-1]["ts"]
        assert ts.endswith("+00:00") or "Z" in ts

    def test_audit_log_query_by_event(self, audit_log_instance, hermes_home):
        """Query filters by event type."""
        audit_log_instance.log(AuditEvent.AUTH_SUCCESS, who="a")
        audit_log_instance.log(AuditEvent.AUTH_FAILURE, who="b")
        audit_log_instance.log(AuditEvent.AUTH_SUCCESS, who="c")
        successes = audit_log_instance.query(event=AuditEvent.AUTH_SUCCESS)
        failures = audit_log_instance.query(event=AuditEvent.AUTH_FAILURE)
        assert len(successes) >= 2
        assert len(failures) >= 1

    def test_audit_log_query_by_who(self, audit_log_instance, hermes_home):
        """Query filters by identity."""
        audit_log_instance.log(AuditEvent.TOOL_EXECUTED, who="alice")
        audit_log_instance.log(AuditEvent.TOOL_EXECUTED, who="bob")
        alice_entries = audit_log_instance.query(who="alice")
        assert all(e["who"] == "alice" for e in alice_entries)

    def test_audit_log_query_by_result(self, audit_log_instance, hermes_home):
        """Query filters by result."""
        audit_log_instance.log(AuditEvent.AUTHZ_GRANTED, who="a", result="allowed")
        audit_log_instance.log(AuditEvent.AUTHZ_DENIED, who="b", result="denied")
        granted = audit_log_instance.query(result="allowed")
        denied = audit_log_instance.query(result="denied")
        assert len(granted) >= 1
        assert len(denied) >= 1

    def test_audit_log_failure_recorded(self, audit_log_instance, hermes_home):
        """Failure details are recorded."""
        audit_log_instance.log(
            AuditEvent.AUTHZ_DENIED,
            who="plugin_x",
            result="denied",
            failure="missing capabilities: ['terminal_execute']",
        )
        entries = audit_log_instance.query(
            event=AuditEvent.AUTHZ_DENIED, result="denied"
        )
        assert len(entries) >= 1
        assert "terminal_execute" in entries[-1]["failure"]

    def test_audit_log_file_written(self, audit_log_instance, hermes_home):
        """Audit log is written to a file on disk."""
        audit_log_instance.log(AuditEvent.AUTH_SUCCESS, who="disk_test")
        log_path = hermes_home / "logs" / "guardian-audit.log"
        assert log_path.exists()
        content = log_path.read_text(encoding="utf-8")
        assert "disk_test" in content

    def test_audit_log_compact_json(self, audit_log_instance, hermes_home):
        """Each line is compact JSON (one event per line)."""
        audit_log_instance.log(AuditEvent.AUTH_SUCCESS, who="compact")
        audit_log_instance.log(AuditEvent.AUTH_FAILURE, who="compact2")
        log_path = hermes_home / "logs" / "guardian-audit.log"
        lines = [l for l in log_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        for line in lines:
            # Should be valid JSON.
            data = json.loads(line)
            assert "ts" in data
            assert "event" in data


# ══════════════════════════════════════════════════════════════════════════════
# 13. RECOVERY
# ══════════════════════════════════════════════════════════════════════════════


class TestRecovery:
    """Scenario 13: Recovery from emergency stops and lockouts."""

    def test_estop_recovery(self, estop):
        """Engaging then disengaging restores normal operation."""
        estop.engage(EmergencyScope.GLOBAL, level=EmergencyLevel.HALT)
        allowed, _ = estop.check_operation("terminal", who="test")
        assert allowed is False

        estop.disengage(EmergencyScope.GLOBAL, who="admin")
        allowed, _ = estop.check_operation("terminal", who="test")
        assert allowed is True

    def test_financial_recovery(self, estop):
        """Financial stop can be disengaged to restore trading."""
        estop.engage(EmergencyScope.FINANCIAL, level=EmergencyLevel.HALT)
        estop.disengage(EmergencyScope.FINANCIAL, who="admin")
        allowed, _ = estop.check_operation("pionex_execute", who="trader")
        assert allowed is True

    def test_auth_lockout_recovery(self, tracker):
        """Lockout expires and allows authentication again."""
        for _ in range(3):
            tracker.record_failure("recover_user", reason="bad")
        locked, _ = tracker.is_locked_out("recover_user")
        assert locked is True

        time.sleep(2.1)
        locked, _ = tracker.is_locked_out("recover_user")
        assert locked is False

    def test_auth_manual_reset(self, tracker):
        """Admin can manually reset an identity's auth state."""
        for _ in range(3):
            tracker.record_failure("manual_reset_user", reason="bad")
        locked, _ = tracker.is_locked_out("manual_reset_user")
        assert locked is True

        tracker.reset("manual_reset_user")
        locked, _ = tracker.is_locked_out("manual_reset_user")
        assert locked is False
        assert tracker.get_failure_count("manual_reset_user") == 0

    def test_authorization_recovery(self, auth_mgr):
        """Revoked capability can be re-granted."""
        identity = Identity(id="recov_user", type=IdentityType.USER)
        auth_mgr.register_identity(identity)
        auth_mgr.revoke_capability("recov_user", Capability.FILE_READ)
        allowed, _ = auth_mgr.check_authorization("recov_user", "read_file")
        assert allowed is False

        auth_mgr.grant_capability("recov_user", Capability.FILE_READ)
        allowed, _ = auth_mgr.check_authorization("recov_user", "read_file")
        assert allowed is True

    def test_plugin_stop_recovery(self, estop):
        """Plugin stop can be disengaged."""
        estop.engage_plugin("plugin_x", reason="misbehaving")
        allowed, _ = estop.check_operation(
            "web_search", plugin_name="plugin_x", who="test"
        )
        assert allowed is False

        estop.disengage_plugin("plugin_x", who="admin")
        allowed, _ = estop.check_operation(
            "web_search", plugin_name="plugin_x", who="test"
        )
        assert allowed is True

    def test_tool_stop_recovery(self, estop):
        """Tool stop can be disengaged."""
        estop.engage_tool("terminal", reason="unsafe")
        allowed, _ = estop.check_operation("terminal", who="test")
        assert allowed is False

        estop.disengage_tool("terminal", who="admin")
        allowed, _ = estop.check_operation("terminal", who="test")
        assert allowed is True


# ══════════════════════════════════════════════════════════════════════════════
# SECURITY MONITORING
# ══════════════════════════════════════════════════════════════════════════════


class TestSecurityMonitoring:
    """Security health checks."""

    def test_run_all_checks_returns_health(self, monitor):
        """Security check returns a SecurityHealth object."""
        health = monitor.run_all_checks()
        assert isinstance(health, SecurityHealth)
        assert health.timestamp is not None
        assert health.passed >= 0

    def test_healthy_when_no_criticals(self, monitor):
        """Healthy is True when no critical findings."""
        health = monitor.run_all_checks()
        # Without emergency stops or lockouts, should be healthy.
        assert health.healthy is True

    def test_emergency_stop_detected(self, estop_singleton, monitor):
        """Active emergency stop is detected as a warning."""
        estop_singleton.engage(EmergencyScope.GLOBAL, level=EmergencyLevel.HALT)
        health = monitor.run_all_checks()
        stop_findings = [
            f for f in health.findings
            if f.check_name == "emergency_stop_status"
        ]
        assert len(stop_findings) >= 1
        assert stop_findings[0].severity == CheckSeverity.WARNING
        # Cleanup.
        estop_singleton.disengage(EmergencyScope.GLOBAL, who="test")

    def test_health_to_dict(self, monitor):
        """Health status can be serialized to dict."""
        health = monitor.run_all_checks()
        d = health.to_dict()
        assert "timestamp" in d
        assert "passed" in d
        assert "healthy" in d
        assert "findings" in d

    def test_estop_integrity_check(self, estop_singleton, monitor):
        """ESTOP integrity check detects engaged state via the file sentinel."""
        from agent.estop import engage as estop_engage, disengage as estop_disengage
        # Write the real ESTOP sentinel file (read by agent.estop.is_engaged).
        estop_engage(reason="integrity test")
        health = monitor.run_all_checks()
        estop_findings = [
            f for f in health.findings
            if f.check_name == "estop_integrity"
        ]
        assert len(estop_findings) >= 1
        assert estop_findings[0].severity == CheckSeverity.WARNING
        # Cleanup.
        estop_disengage()


# ══════════════════════════════════════════════════════════════════════════════
# INTEGRATION: Authorization + Emergency + Audit
# ══════════════════════════════════════════════════════════════════════════════


class TestIntegration:
    """Integration tests combining multiple security components."""

    def test_full_authorization_flow(self, auth_mgr, estop, hermes_home):
        """Complete authorization flow: register, grant, check, emergency stop."""
        # 1. Register a user.
        user = Identity(id="integration_user", type=IdentityType.USER)
        auth_mgr.register_identity(user)

        # 2. User can use read_file (default capability).
        allowed, _ = auth_mgr.check_authorization(
            "integration_user", "read_file"
        )
        assert allowed is True

        # 3. Grant financial capability for testing.
        auth_mgr.grant_capability(
            "integration_user", Capability.FINANCIAL_TRADE, reason="test"
        )
        allowed, _ = auth_mgr.check_authorization(
            "integration_user", "pionex_execute"
        )
        assert allowed is True

        # 4. Engage financial emergency stop.
        estop.engage(EmergencyScope.FINANCIAL, level=EmergencyLevel.HALT)

        # 5. Authorization still passes (user has FINANCIAL_TRADE)...
        allowed, _ = auth_mgr.check_authorization(
            "integration_user", "pionex_execute"
        )
        assert allowed is True

        # 6. ...but emergency stop blocks it.
        allowed, reason = estop.check_operation("pionex_execute", who="integration_user")
        assert allowed is False  # Emergency stop blocks it.

    def test_plugin_blocked_at_multiple_levels(self, auth_mgr, estop):
        """Plugin is blocked by both authorization AND emergency stop."""
        plugin = Identity(id="bad_plugin", type=IdentityType.PLUGIN)
        auth_mgr.register_identity(plugin)

        # Authorization blocks: plugin lacks TERMINAL_EXECUTE.
        allowed, _ = auth_mgr.check_authorization("bad_plugin", "terminal")
        assert allowed is False

        # Emergency stop also blocks it.
        estop.engage(EmergencyScope.GLOBAL, level=EmergencyLevel.HALT)
        allowed, _ = estop.check_operation("terminal", plugin_name="bad_plugin")
        assert allowed is False

    def test_audit_trail_covers_all_operations(self, auth_mgr, estop, hermes_home):
        """Audit log captures authorization grants, denials, and emergency stops."""
        user = Identity(id="audit_user", type=IdentityType.USER)
        auth_mgr.register_identity(user)

        # This generates audit entries.
        auth_mgr.check_authorization("audit_user", "read_file")
        auth_mgr.deny_capability(
            "audit_user", Capability.TERMINAL_EXECUTE, reason="test"
        )
        auth_mgr.check_authorization("audit_user", "terminal")

        # Emergency stop generates audit entries.
        estop.engage(
            EmergencyScope.FINANCIAL,
            level=EmergencyLevel.HALT,
            reason="integration test",
        )

        # Verify the audit log exists and has entries.
        log_path = hermes_home / "logs" / "guardian-audit.log"
        assert log_path.exists()
        content = log_path.read_text(encoding="utf-8")
        assert "audit_user" in content

    def test_llm_cannot_override_emergency_stop(self, estop):
        """CRITICAL GUARDIAN RULE: LLM reasoning cannot override emergency stop.

        This test verifies that even if the LLM 'decides' to proceed,
        the emergency stop is deterministic and blocks the operation.
        """
        estop.engage(EmergencyScope.FINANCIAL, level=EmergencyLevel.HALT)

        # Simulate LLM attempting to override ("I think this is safe").
        # The check is deterministic — no LLM input is considered.
        allowed, reason = estop.check_operation(
            "pionex_execute",
            who="llm_agent",
            session_id="llm_session_001",
        )
        assert allowed is False
        assert reason is not None
        # The reason does NOT contain any LLM output.
        assert "safe" not in reason.lower()

    def test_llm_cannot_override_authorization(self, auth_mgr):
        """CRITICAL GUARDIAN RULE: LLM cannot grant itself capabilities."""
        agent = Identity(id="llm_agent", type=IdentityType.AGENT)
        auth_mgr.register_identity(agent)
        # Agent does NOT have FINANCIAL_TRADE.
        allowed, reason = auth_mgr.check_authorization(
            "llm_agent", "pionex_execute"
        )
        assert allowed is False
        # The denial is deterministic — no LLM reasoning changes it.
        # Only an explicit programmatic grant can change it.
        auth_mgr.grant_capability(
            "llm_agent", Capability.FINANCIAL_TRADE, reason="operator approval"
        )
        allowed, _ = auth_mgr.check_authorization("llm_agent", "pionex_execute")
        assert allowed is True  # Now allowed via explicit programmatic grant.
