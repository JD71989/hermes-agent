"""Guardian Security Department for Hermes Agent.

Provides the unified security layer for the Guardian 2 architecture:

- **Audit logging**: Structured, tamper-evident security event trail
  with WHO/WHAT/WHEN/WHY/ACTION/RESULT/FAILURE fields.
- **Authorization**: Capability-based permission system for tools,
  agents, plugins, and privileged operations.
- **Auth tracking**: Failed authentication tracking with lockout.
- **Emergency controls**: Granular per-component emergency stops.
- **Security monitoring**: Runtime health and anomaly detection.

All modules are profile-aware (``get_hermes_home()``) and thread-safe.
LLM reasoning must NEVER override any control enforced here.
"""

from agent.guardian.audit import (
    AuditEvent,
    audit_log,
    query_audit_log,
    SecurityAuditLog,
)
from agent.guardian.authorization import (
    Capability,
    Identity,
    IdentityType,
    AuthorizationManager,
    authorization_manager,
    check_authorization,
    grant_capability,
    revoke_capability,
)
from agent.guardian.auth_tracker import (
    AuthTracker,
    auth_tracker,
    record_auth_failure,
    record_auth_success,
    is_locked_out,
)
from agent.guardian.emergency import (
    EmergencyLevel,
    EmergencyScope,
    EmergencyStop,
    emergency_stop,
    engage_emergency_stop,
    disengage_emergency_stop,
    is_operation_allowed,
)
from agent.guardian.monitoring import (
    SecurityMonitor,
    SecurityHealth,
    security_monitor,
    run_security_check,
)

__all__ = [
    # Audit
    "AuditEvent",
    "audit_log",
    "query_audit_log",
    "SecurityAuditLog",
    # Authorization
    "Capability",
    "Identity",
    "IdentityType",
    "AuthorizationManager",
    "authorization_manager",
    "check_authorization",
    "grant_capability",
    "revoke_capability",
    # Auth tracking
    "AuthTracker",
    "auth_tracker",
    "record_auth_failure",
    "record_auth_success",
    "is_locked_out",
    # Emergency
    "EmergencyLevel",
    "EmergencyScope",
    "EmergencyStop",
    "emergency_stop",
    "engage_emergency_stop",
    "disengage_emergency_stop",
    "is_operation_allowed",
    # Monitoring
    "SecurityMonitor",
    "SecurityHealth",
    "security_monitor",
    "run_security_check",
]
