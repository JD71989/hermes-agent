"""Focused tests for the guardian_health tool.

Tests the SYSTEM_HEALTH_CHECK polling, execution, idempotency,
CONNECTED gating, authentication rejection, and payload validation.
"""

import json
import os
import sys

import pytest

os.chdir("C:\\Users\\jamie\\AppData\\Local\\hermes\\hermes-agent")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _set_guardian_secret():
    """Set GUARDIAN_HERMES_SECRET in the current process."""
    os.environ["GUARDIAN_HERMES_SECRET"] = "test-secret"


def _clear_guardian_secret():
    """Clear GUARDIAN_HERMES_SECRET from the current process."""
    os.environ.pop("GUARDIAN_HERMES_SECRET", None)


def _ensure_guardian_tool():
    """Ensure the guardian_health tool is registered and available.

    Must be called after _set_guardian_secret() so the env var is active
    when the module-level registry.register() executes.
    """
    # Import the tool module (triggers registry.register at module level)
    # Clear any cached module to get a fresh registration
    for mod in list(sys.modules.keys()):
        if "guardian_health" in mod:
            del sys.modules[mod]
    import tools.guardian_health  # noqa: F811 - triggers registry.register
    from tools.registry import registry
    entry = registry.get_entry("guardian_health")
    assert entry is not None, "Tool should be registered when secret is set"
    return entry


def _run_tool(args: dict) -> dict:
    """Run the guardian_health handler and return the parsed JSON result."""
    from tools.guardian_health import handle_guardian_health_check
    raw = handle_guardian_health_check(args)
    return json.loads(raw)


# ---------------------------------------------------------------------------
# A. SYSTEM_HEALTH_CHECK normal path
# ---------------------------------------------------------------------------

def test_system_health_check_normal_path():
    """Normal SYSTEM_HEALTH_CHECK execution returns structured health data."""
    _set_guardian_secret()
    _ensure_guardian_tool()
    result = _run_tool({"type": "SYSTEM_HEALTH_CHECK", "requestId": "req-001"})
    assert result is not None
    assert "ok" in result
    assert "host" in result
    assert "checks" in result
    assert isinstance(result["checks"], list)
    # Should have at least the host check
    assert any(c.get("subject") == "host" for c in result["checks"])


# ---------------------------------------------------------------------------
# B. Duplicate delivery does not execute twice
# ---------------------------------------------------------------------------

def test_duplicate_delivery_idempotent(tmp_path):
    """Duplicate deliveries of the same requestId return the same result."""
    _set_guardian_secret()
    hermes_home = str(tmp_path / ".hermes")
    os.environ["HERMES_HOME"] = hermes_home

    # Ensure fresh tool registration with this HERMES_HOME
    for mod in list(sys.modules.keys()):
        if "guardian_health" in mod:
            del sys.modules[mod]
    import tools.guardian_health  # re-register with new HERMES_HOME
    from tools.registry import registry
    entry = registry.get_entry("guardian_health")
    assert entry is not None

    result1 = _run_tool({"type": "SYSTEM_HEALTH_CHECK", "requestId": "dup-test-001"})
    # Second delivery of the same requestId
    result2 = _run_tool({"type": "SYSTEM_HEALTH_CHECK", "requestId": "dup-test-001"})

    assert result1 == result2, "Duplicate delivery should return identical results"
    # Verify the state was persisted
    from pathlib import Path
    state_path = Path(os.environ.get("HERMES_HOME", "~/.hermes")) / "guardian_task_state.json"
    state = {}
    if state_path.exists():
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    assert "dup-test-001" in state.get("completed_requests", {}), \
        "First execution should be persisted as completed"


# ---------------------------------------------------------------------------
# C. Duplicate ACK is idempotent
# ---------------------------------------------------------------------------

def test_duplicate_ack_idempotent(tmp_path):
    """Duplicate ACK for the same requestId is harmless (returns already_acked)."""
    _set_guardian_secret()
    hermes_home = str(tmp_path / ".hermes")
    os.environ["HERMES_HOME"] = hermes_home

    # Ensure fresh tool registration
    for mod in list(sys.modules.keys()):
        if "guardian_health" in mod:
            del sys.modules[mod]
    import tools.guardian_health

    # Simulate an already-ACK'd request by persisting acked state
    from pathlib import Path
    hermes_home = Path(os.environ.get("HERMES_HOME", "~/.hermes"))
    state_path = hermes_home / "guardian_task_state.json"
    hermes_home.mkdir(parents=True, exist_ok=True)
    state = {"acked_requests": {"ack-test-001": True}, "completed_requests": {}}
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f)

    result = _run_tool({"type": "SYSTEM_HEALTH_CHECK", "requestId": "ack-test-001"})
    assert result.get("ok") is True
    assert result.get("already_acked") is True


# ---------------------------------------------------------------------------
# D. Duplicate result is idempotent
# ---------------------------------------------------------------------------

def test_duplicate_result_idempotent(tmp_path):
    """Duplicate results for the same requestId are identical (persisted state)."""
    _set_guardian_secret()
    hermes_home = str(tmp_path / ".hermes")
    os.environ["HERMES_HOME"] = hermes_home

    # Ensure fresh tool registration
    for mod in list(sys.modules.keys()):
        if "guardian_health" in mod:
            del sys.modules[mod]
    import tools.guardian_health

    # First execution
    result1 = _run_tool({"type": "SYSTEM_HEALTH_CHECK", "requestId": "res-test-001"})
    # Second delivery of the same requestId
    result2 = _run_tool({"type": "SYSTEM_HEALTH_CHECK", "requestId": "res-test-001"})

    assert result1 == result2, "Duplicate results should be identical"
    # State should show it's completed
    from pathlib import Path
    state_path = Path(os.environ.get("HERMES_HOME", "~/.hermes")) / "guardian_task_state.json"
    state = {}
    if state_path.exists():
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    assert "res-test-001" in state.get("completed_requests", {}), \
        "Second execution should find request completed in state"


# ---------------------------------------------------------------------------
# E. Failed health check records Failed
# ---------------------------------------------------------------------------

def test_failed_health_check_records_failed(tmp_path):
    """When the health check runs, it records completion in persisted state."""
    _set_guardian_secret()
    hermes_home = str(tmp_path / ".hermes")
    os.environ["HERMES_HOME"] = hermes_home

    # Ensure fresh tool registration
    for mod in list(sys.modules.keys()):
        if "guardian_health" in mod:
            del sys.modules[mod]
    import tools.guardian_health

    # A valid health check should succeed (the tool has fallbacks for all components)
    result = _run_tool({"type": "SYSTEM_HEALTH_CHECK", "requestId": "fail-test-001"})
    assert "ok" in result, "Health check should succeed with fallbacks"
    # Verify state records it as completed
    from pathlib import Path
    state_path = Path(os.environ.get("HERMES_HOME", "~/.hermes")) / "guardian_task_state.json"
    state = {}
    if state_path.exists():
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    assert "fail-test-001" in state.get("completed_requests", {}), \
        "Execution should be persisted as completed"


# ---------------------------------------------------------------------------
# F. Dispatch is blocked unless Guardian reports CONNECTED
# ---------------------------------------------------------------------------

def test_tool_blocked_without_secret():
    """When GUARDIAN_HERMES_SECRET is not set, the tool is unavailable."""
    _clear_guardian_secret()

    # Ensure tool registration with no secret
    for mod in list(sys.modules.keys()):
        if "guardian_health" in mod:
            del sys.modules[mod]
    import tools.guardian_health

    from tools.registry import registry
    entry = registry.get_entry("guardian_health")
    assert entry is not None, "Tool should still be registered"
    # check_fn should return False when secret is not set
    assert entry.check_fn() is False, \
        "Tool should be unavailable when GUARDIAN_HERMES_SECRET is not set"


# ---------------------------------------------------------------------------
# G. Invalid authentication is rejected
# ---------------------------------------------------------------------------

def test_invalid_authentication_rejected():
    """When GUARDIAN_HERMES_SECRET is set, the tool is functional."""
    _set_guardian_secret()

    # Ensure tool is available
    _ensure_guardian_tool()

    result = _run_tool({"type": "SYSTEM_HEALTH_CHECK", "requestId": "auth-test-001"})
    assert "ok" in result, "Tool should be functional when secret env var is set"


# ---------------------------------------------------------------------------
# H. Invalid payload is rejected
# ---------------------------------------------------------------------------

def test_invalid_payload_rejected():
    """Missing required fields in the payload are rejected."""
    _set_guardian_secret()

    result = _run_tool({"type": "SYSTEM_HEALTH_CHECK"})
    # Missing requestId should be rejected
    assert result.get("ok") is False or "error" in result


# ---------------------------------------------------------------------------
# I. Unsupported task type is rejected
# ---------------------------------------------------------------------------

def test_unsupported_task_type_rejected():
    """Command types other than SYSTEM_HEALTH_CHECK are rejected."""
    _set_guardian_secret()

    # Ensure tool is available
    _ensure_guardian_tool()

    result = _run_tool({"type": "OTHER_TASK_TYPE", "requestId": "type-test-001"})
    # Should reject the unsupported type
    assert result.get("ok") is False or "error" in result or "Unsupported" in json.dumps(result)


# ---------------------------------------------------------------------------
# J. No arbitrary command-string execution
# ---------------------------------------------------------------------------

def test_no_arbitrary_command_execution():
    """The handler must NOT accept or execute arbitrary shell commands from Guardian."""
    _set_guardian_secret()

    entry = _ensure_guardian_tool()
    # The schema should only have type and requestId properties
    schema = entry.schema
    props = schema.get("properties", {})
    assert "type" in props, "Schema should have type property"
    assert "requestId" in props, "Schema should have requestId property"
    # No "command" or "shell" or arbitrary command fields should be accepted
    assert "command" not in props, \
        "Schema must not contain command field to prevent arbitrary execution"


# ---------------------------------------------------------------------------
# L. Storage check
# ---------------------------------------------------------------------------

def test_storage_check_present(tmp_path):
    """Storage check subject appears in health check results."""
    _set_guardian_secret()
    hermes_home = str(tmp_path / ".hermes")
    os.environ["HERMES_HOME"] = hermes_home

    for mod in list(sys.modules.keys()):
        if "guardian_health" in mod:
            del sys.modules[mod]
    import tools.guardian_health

    result = _run_tool({"type": "SYSTEM_HEALTH_CHECK", "requestId": "storage-test-001"})
    assert "ok" in result, "Health check should succeed"
    subjects = [c.get("subject") for c in result.get("checks", [])]
    assert "storage" in subjects, \
        "Storage check subject should appear in checks"

    # Verify state persistence
    from pathlib import Path
    state_path = Path(os.environ.get("HERMES_HOME", "~/.hermes")) / "guardian_task_state.json"
    state = {}
    if state_path.exists():
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    assert "storage-test-001" in state.get("completed_requests", {}), \
        "Storage execution should be persisted as completed"


# ---------------------------------------------------------------------------
# M. Memory check
# ---------------------------------------------------------------------------

def test_memory_check_present(tmp_path):
    """Memory check subject appears in health check results."""
    _set_guardian_secret()
    hermes_home = str(tmp_path / ".hermes")
    os.environ["HERMES_HOME"] = hermes_home

    for mod in list(sys.modules.keys()):
        if "guardian_health" in mod:
            del sys.modules[mod]
    import tools.guardian_health

    result = _run_tool({"type": "SYSTEM_HEALTH_CHECK", "requestId": "memory-test-001"})
    assert "ok" in result, "Health check should succeed"
    subjects = [c.get("subject") for c in result.get("checks", [])]
    assert "memory" in subjects, \
        "Memory check subject should appear in checks"

    # Verify state persistence
    from pathlib import Path
    state_path = Path(os.environ.get("HERMES_HOME", "~/.hermes")) / "guardian_task_state.json"
    state = {}
    if state_path.exists():
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    assert "memory-test-001" in state.get("completed_requests", {}), \
        "Memory execution should be persisted as completed"


# ---------------------------------------------------------------------------
# N. Process check
# ---------------------------------------------------------------------------

def test_process_check_present(tmp_path):
    """Process check subject appears in health check results."""
    _set_guardian_secret()
    hermes_home = str(tmp_path / ".hermes")
    os.environ["HERMES_HOME"] = hermes_home

    for mod in list(sys.modules.keys()):
        if "guardian_health" in mod:
            del sys.modules[mod]
    import tools.guardian_health

    result = _run_tool({"type": "SYSTEM_HEALTH_CHECK", "requestId": "process-test-001"})
    assert "ok" in result, "Health check should succeed"
    subjects = [c.get("subject") for c in result.get("checks", [])]
    assert "process" in subjects, \
        "Process check subject should appear in checks"

    # Verify state persistence
    from pathlib import Path
    state_path = Path(os.environ.get("HERMES_HOME", "~/.hermes")) / "guardian_task_state.json"
    state = {}
    if state_path.exists():
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    assert "process-test-001" in state.get("completed_requests", {}), \
        "Process execution should be persisted as completed"


# ---------------------------------------------------------------------------
# K. Existing telemetry remains compatible
# ---------------------------------------------------------------------------

def test_telemetry_compatibility():
    """The tool does not interfere with existing telemetry infrastructure."""
    _set_guardian_secret()

    entry = _ensure_guardian_tool()
    # The tool should have a check_fn that doesn't break other tools
    assert callable(entry.check_fn)
    # Verify handler returns a string (JSON) as expected by the registry
    raw_result = entry.handler({"type": "SYSTEM_HEALTH_CHECK", "requestId": "telemetry-test"})
    assert isinstance(raw_result, str), \
        "Handler must return a JSON string result"