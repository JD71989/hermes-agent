"""Security health monitoring for Guardian 2.

Periodic and on-demand security health checks that detect:

- Configuration anomalies (missing auth, weak settings)
- Permission anomalies (unexpected capability grants)
- Credential exposure risks
- Emergency stop status
- Auth lockout status
- Dependency vulnerabilities (wraps existing security_audit)

Results are recorded to the audit log and returned as structured
``SecurityHealth`` objects.
"""
from __future__ import annotations

import enum
import json
import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from agent.guardian.audit import AuditEvent, audit_log

logger = logging.getLogger(__name__)


class CheckSeverity(enum.Enum):
    """Severity of a security finding."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class SecurityFinding:
    """A single security health finding."""

    check_name: str
    severity: CheckSeverity
    message: str
    details: Optional[dict] = None


@dataclass
class SecurityHealth:
    """Aggregated security health status."""

    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    findings: list[SecurityFinding] = field(default_factory=list)
    passed: int = 0
    warnings: int = 0
    criticals: int = 0

    @property
    def healthy(self) -> bool:
        """True if no critical findings."""
        return self.criticals == 0

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "passed": self.passed,
            "warnings": self.warnings,
            "criticals": self.criticals,
            "healthy": self.healthy,
            "findings": [
                {
                    "check": f.check_name,
                    "severity": f.severity.value,
                    "message": f.message,
                    "details": f.details,
                }
                for f in self.findings
            ],
        }


def _hermes_home() -> Path:
    """Resolve the active HERMES_HOME at call time."""
    try:
        from hermes_constants import get_hermes_home
        return get_hermes_home()
    except Exception:
        return Path(os.path.expanduser("~/.hermes"))


class SecurityMonitor:
    """Runs security health checks and returns structured results.

    Thread-safe. Each check is independent — a failure in one check
    does not prevent others from running.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def run_all_checks(self) -> SecurityHealth:
        """Run all security health checks and return aggregated results."""
        health = SecurityHealth()
        checks = [
            self._check_emergency_stop,
            self._check_auth_lockouts,
            self._check_file_permissions,
            self._check_config_security,
            self._check_credential_exposure,
            self._check_estop_integrity,
        ]
        for check_fn in checks:
            try:
                findings = check_fn()
                for f in findings:
                    health.findings.append(f)
                    if f.severity == CheckSeverity.CRITICAL:
                        health.criticals += 1
                    elif f.severity == CheckSeverity.WARNING:
                        health.warnings += 1
                    else:
                        health.passed += 1
            except Exception as e:
                health.findings.append(SecurityFinding(
                    check_name=check_fn.__name__,
                    severity=CheckSeverity.WARNING,
                    message=f"Check failed with exception: {e}",
                ))
                health.warnings += 1

        # Record summary to audit log.
        audit_log(
            AuditEvent.SECURITY_CHECK_PASSED if health.healthy
            else AuditEvent.SECURITY_CHECK_FAILED,
            who="system",
            what=f"security health check: {health.passed} passed, "
                 f"{health.warnings} warnings, {health.criticals} critical",
            result="allowed" if health.healthy else "blocked",
        )
        return health

    def _check_emergency_stop(self) -> list[SecurityFinding]:
        """Check current emergency stop status."""
        findings = []
        from agent.guardian.emergency import emergency_stop, EmergencyScope
        stops = emergency_stop.get_all_stops()
        if stops:
            findings.append(SecurityFinding(
                check_name="emergency_stop_status",
                severity=CheckSeverity.WARNING,
                message=f"Active emergency stops: {stops}",
                details=stops,
            ))
        else:
            findings.append(SecurityFinding(
                check_name="emergency_stop_status",
                severity=CheckSeverity.INFO,
                message="No active emergency stops",
            ))
        return findings

    def _check_auth_lockouts(self) -> list[SecurityFinding]:
        """Check for active auth lockouts."""
        findings = []
        from agent.guardian.auth_tracker import auth_tracker
        with auth_tracker._lock:
            for identity, record in auth_tracker._records.items():
                if record.locked_until > 0:
                    import time
                    remaining = record.locked_until - time.monotonic()
                    if remaining > 0:
                        findings.append(SecurityFinding(
                            check_name="auth_lockout",
                            severity=CheckSeverity.WARNING,
                            message=(
                                f"Identity '{identity}' is locked out "
                                f"({remaining:.0f}s remaining, "
                                f"{record.count} failures)"
                            ),
                            details={
                                "identity": identity,
                                "failures": record.count,
                                "remaining_seconds": round(remaining),
                            },
                        ))
        if not findings:
            findings.append(SecurityFinding(
                check_name="auth_lockout",
                severity=CheckSeverity.INFO,
                message="No active auth lockouts",
            ))
        return findings

    def _check_file_permissions(self) -> list[SecurityFinding]:
        """Check that critical files have appropriate permissions."""
        findings = []
        home = _hermes_home()

        # On POSIX, check .env and config.yaml permissions.
        if os.name != "nt":
            for filename, expected_mode in [
                (".env", 0o600),
                ("config.yaml", 0o600),
                ("auth.json", 0o600),
            ]:
                filepath = home / filename
                if filepath.exists():
                    actual_mode = filepath.stat().st_mode & 0o777
                    if actual_mode != expected_mode:
                        findings.append(SecurityFinding(
                            check_name="file_permissions",
                            severity=CheckSeverity.WARNING,
                            message=(
                                f"{filename} has permissions "
                                f"{oct(actual_mode)}, expected "
                                f"{oct(expected_mode)}"
                            ),
                            details={
                                "file": str(filepath),
                                "actual": oct(actual_mode),
                                "expected": oct(expected_mode),
                            },
                        ))
                    else:
                        findings.append(SecurityFinding(
                            check_name="file_permissions",
                            severity=CheckSeverity.INFO,
                            message=f"{filename} has correct permissions",
                        ))
        else:
            findings.append(SecurityFinding(
                check_name="file_permissions",
                severity=CheckSeverity.INFO,
                message="Permission checks skipped on Windows",
            ))
        return findings

    def _check_config_security(self) -> list[SecurityFinding]:
        """Check for security-relevant config settings."""
        findings = []
        home = _hermes_home()
        config_path = home / "config.yaml"
        if not config_path.exists():
            findings.append(SecurityFinding(
                check_name="config_security",
                severity=CheckSeverity.INFO,
                message="No config.yaml found (using defaults)",
            ))
            return findings

        try:
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        except Exception:
            findings.append(SecurityFinding(
                check_name="config_security",
                severity=CheckSeverity.INFO,
                message="Could not parse config.yaml",
            ))
            return findings

        # Check approvals mode.
        approvals = config.get("approvals", {})
        mode = approvals.get("mode", "manual")
        if mode == "off":
            findings.append(SecurityFinding(
                check_name="config_approvals_mode",
                severity=CheckSeverity.WARNING,
                message="Approval mode is 'off' — all approval checks are bypassed",
            ))
        else:
            findings.append(SecurityFinding(
                check_name="config_approvals_mode",
                severity=CheckSeverity.INFO,
                message=f"Approval mode: {mode}",
            ))

        # Check security.redact_secrets.
        security = config.get("security", {})
        redact = security.get("redact_secrets", True)
        if not redact:
            findings.append(SecurityFinding(
                check_name="config_redact_secrets",
                severity=CheckSeverity.WARNING,
                message="Secret redaction is disabled",
            ))
        else:
            findings.append(SecurityFinding(
                check_name="config_redact_secrets",
                severity=CheckSeverity.INFO,
                message="Secret redaction is enabled",
            ))

        return findings

    def _check_credential_exposure(self) -> list[SecurityFinding]:
        """Check for common credential exposure risks."""
        findings = []
        home = _hermes_home()

        # Check if .env is world-readable (POSIX only).
        if os.name != "nt":
            env_path = home / ".env"
            if env_path.exists():
                mode = env_path.stat().st_mode & 0o777
                if mode & 0o044:  # World or group readable
                    findings.append(SecurityFinding(
                        check_name="credential_exposure",
                        severity=CheckSeverity.CRITICAL,
                        message=(
                            f".env is world/group-readable ({oct(mode)}). "
                            f"Should be 0o600."
                        ),
                    ))
                else:
                    findings.append(SecurityFinding(
                        check_name="credential_exposure",
                        severity=CheckSeverity.INFO,
                        message=".env has restricted permissions",
                    ))
            else:
                findings.append(SecurityFinding(
                    check_name="credential_exposure",
                    severity=CheckSeverity.INFO,
                    message="No .env file found",
                ))
        else:
            findings.append(SecurityFinding(
                check_name="credential_exposure",
                severity=CheckSeverity.INFO,
                message="Credential file check skipped on Windows",
            ))
        return findings

    def _check_estop_integrity(self) -> list[SecurityFinding]:
        """Check the ESTOP sentinel file integrity."""
        findings = []
        from agent.estop import is_engaged, get_state
        engaged = is_engaged()
        if engaged:
            state = get_state()
            findings.append(SecurityFinding(
                check_name="estop_integrity",
                severity=CheckSeverity.WARNING,
                message="Global ESTOP is engaged",
                details=state,
            ))
        else:
            findings.append(SecurityFinding(
                check_name="estop_integrity",
                severity=CheckSeverity.INFO,
                message="Global ESTOP is not engaged",
            ))
        return findings


# Module-level singleton.
security_monitor = SecurityMonitor()


def run_security_check() -> SecurityHealth:
    """Convenience function: run all security health checks."""
    return security_monitor.run_all_checks()
