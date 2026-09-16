"""``hermes guardian`` subcommand — unified Guardian verification and control.

Provides a single operator command capable of performing a complete Guardian
verification across all subsystems. Also supports subcommands for status,
health, and maintenance.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class GuardianStatus(Enum):
    PASS = "PASS"
    BLOCKED = "BLOCKED"
    FAIL = "FAIL"
    DEFERRED = "DEFERRED"


class GuardianVerificationResult:
    """Aggregated result of a Guardian verification run."""

    def __init__(self) -> None:
        self.timestamp: str = datetime.now(timezone.utc).isoformat()
        self.subsystem_statuses: dict[str, GuardianStatus] = {}
        self.tests_run: int = 0
        self.tests_passed: int = 0
        self.tests_failed: int = 0
        self.tests_blocked: int = 0
        self.failures: list[dict[str, Any]] = []
        self.blocked_dependencies: list[dict[str, Any]] = []
        self.security_lock_state: dict[str, Any] = {}
        self.recommended_next_action: str = ""
        self.overall: GuardianStatus = GuardianStatus.PASS

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "subsystem_statuses": {
                k: v.value for k, v in self.subsystem_statuses.items()
            },
            "tests_run": self.tests_run,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "tests_blocked": self.tests_blocked,
            "overall": self.overall.value,
            "failures": self.failures,
            "blocked_dependencies": self.blocked_dependencies,
            "security_lock_state": self.security_lock_state,
            "recommended_next_action": self.recommended_next_action,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


# ── Core subsystem checks ─────────────────────────────────────────────


def _check_python_runtime() -> tuple[GuardianStatus, str]:
    """Check Python/runtime availability."""
    try:
        version = sys.version
        return GuardianStatus.PASS, f"Python {version.split()[0]} OK"
    except Exception as e:
        return GuardianStatus.FAIL, f"Python runtime check failed: {e}"


def _check_imports() -> tuple[GuardianStatus, str]:
    """Check critical imports."""
    missing: list[str] = []
    for mod in ["hermes_constants", "tools.registry", "model_tools",
                "agent.guardian"]:
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        return GuardianStatus.BLOCKED, f"Missing imports: {', '.join(missing)}"
    return GuardianStatus.PASS, "All critical imports available"


def _check_configuration() -> tuple[GuardianStatus, str]:
    """Check configuration validity."""
    try:
        from hermes_cli.config import load_config_readonly
        cfg = load_config_readonly()
        if not isinstance(cfg, dict):
            return GuardianStatus.FAIL, "Config returned non-dict"
        return GuardianStatus.PASS, "Configuration loaded successfully"
    except Exception as e:
        return GuardianStatus.FAIL, f"Configuration error: {e}"


def _check_environment() -> tuple[GuardianStatus, str]:
    """Check environment variables."""
    issues: list[str] = []
    if not os.getenv("HERMES_HOME"):
        issues.append("HERMES_HOME not set")
    if not issues:
        return GuardianStatus.PASS, "Environment OK"
    return GuardianStatus.BLOCKED, "; ".join(issues)


def _check_dependency_health() -> tuple[GuardianStatus, str]:
    """Check dependency health."""
    try:
        import yaml  # noqa: F401
        import sqlite3  # noqa: F401
        import json  # noqa: F401
        return GuardianStatus.PASS, "Core dependencies available"
    except ImportError as e:
        return GuardianStatus.BLOCKED, f"Missing dependency: {e}"


def _check_guardian_security() -> tuple[GuardianStatus, str]:
    """Check Guardian security subsystem."""
    try:
        from agent.guardian import security_monitor, run_security_check
        health = run_security_check()
        if health.healthy:
            return GuardianStatus.PASS, f"Security checks OK ({health.passed} passed)"
        else:
            return GuardianStatus.BLOCKED, f"Security warnings: {health.criticals} critical"
    except Exception as e:
        return GuardianStatus.FAIL, f"Security check failed: {e}"


def _check_guardian_storage() -> tuple[GuardianStatus, str]:
    """Check Guardian storage subsystem."""
    try:
        from hermes_cli.guardian_storage import check_disk_capacity, StorageLevel
        capacity = check_disk_capacity()
        level = capacity.level
        if level in (StorageLevel.CRITICAL, StorageLevel.EMERGENCY):
            return GuardianStatus.BLOCKED, f"Storage emergency: {level.value} ({capacity.free_gb:.1f} GB free)"
        if level in (StorageLevel.HIGH_ALERT,):
            return GuardianStatus.WARNING if hasattr(GuardianStatus, 'WARNING') else GuardianStatus.BLOCKED, f"Storage warning: {level.value}"
        return GuardianStatus.PASS, f"Storage OK ({capacity.free_gb:.1f} GB free, {level.value})"
    except Exception as e:
        return GuardianStatus.FAIL, f"Storage check failed: {e}"


def _check_guardian_recovery() -> tuple[GuardianStatus, str]:
    """Check Guardian recovery subsystem."""
    try:
        from hermes_cli.guardian_recovery import RecoveryStatus
        return GuardianStatus.PASS, "Recovery module available"
    except Exception as e:
        return GuardianStatus.FAIL, f"Recovery check failed: {e}"


def _check_trading() -> tuple[GuardianStatus, str]:
    """Check Trading subsystem."""
    try:
        from agent.nexus import MAX_APPROVED_CAPITAL_USDT
        return GuardianStatus.PASS, f"NEXUS engine available (max capital: ${MAX_APPROVED_CAPITAL_USDT})"
    except ImportError:
        return GuardianStatus.BLOCKED, "NEXUS module not available"
    except Exception as e:
        return GuardianStatus.FAIL, f"Trading check failed: {e}"


def _check_crypto() -> tuple[GuardianStatus, str]:
    """Check Crypto Intelligence subsystem."""
    try:
        from agent.crypto_department.opportunity_store import OpportunityStore
        return GuardianStatus.PASS, "Crypto opportunity store available"
    except ImportError:
        return GuardianStatus.BLOCKED, "Crypto department not available"
    except Exception as e:
        return GuardianStatus.FAIL, f"Crypto check failed: {e}"


def _check_leadgen() -> tuple[GuardianStatus, str]:
    """Check LEADGEN subsystem."""
    try:
        from tools.bond_revenue_tool import check_requirements
        available = check_requirements()
        if available:
            return GuardianStatus.PASS, "Bond/LEADGEN credentials configured"
        else:
            return GuardianStatus.BLOCKED, "BOND_API_KEY not configured"
    except ImportError:
        return GuardianStatus.BLOCKED, "Bond revenue module not available"
    except Exception as e:
        return GuardianStatus.FAIL, f"LEADGEN check failed: {e}"


def _check_economic() -> tuple[GuardianStatus, str]:
    """Check Economic Kernel subsystem."""
    try:
        from hermes_cli.guardian_economic import get_economic_kernel
        kernel = get_economic_kernel()
        # Test basic economic computation to verify it's operational
        from hermes_cli.guardian_economic import EconomicAction
        gate = kernel.compute_economics(
            expected_revenue=100.0,
            expected_cost=50.0,
            risk_score=0.1,
            treasury_impact=25.0,
        )
        # Treasury should have some initial balance or be configured
        treasury = kernel.treasury
        return GuardianStatus.PASS, f"Economic Kernel operational (treasury balance: ${treasury.balance:.2f})"
    except ImportError:
        return GuardianStatus.BLOCKED, "Economic Kernel module not available"
    except Exception as e:
        return GuardianStatus.FAIL, f"Economic check failed: {e}"


def _check_media() -> tuple[GuardianStatus, str]:
    """Check Media Farm subsystem."""
    try:
        from tools.media_farm_db import MediaFarmDB
        return GuardianStatus.PASS, "Media Farm DB available"
    except ImportError:
        return GuardianStatus.BLOCKED, "Media Farm module not available"
    except Exception as e:
        return GuardianStatus.FAIL, f"Media check failed: {e}"


def _check_emergency_stop() -> tuple[GuardianStatus, str]:
    """Check emergency stop state."""
    try:
        from agent.guardian.emergency import emergency_stop, EmergencyScope, EmergencyLevel
        is_engaged, level = emergency_stop.is_engaged(EmergencyScope.GLOBAL)
        if is_engaged and level == EmergencyLevel.HALT:
            return GuardianStatus.BLOCKED, "Global emergency stop is HALT"
        if is_engaged:
            return GuardianStatus.BLOCKED, f"Emergency stop engaged: {level.value}"
        return GuardianStatus.PASS, "No emergency stop active"
    except Exception as e:
        return GuardianStatus.FAIL, f"Emergency stop check failed: {e}"


def _check_authorization() -> tuple[GuardianStatus, str]:
    """Check authorization subsystem."""
    try:
        from agent.guardian.authorization import authorization_manager, Identity, IdentityType
        ident = Identity(id="guardian-check", type=IdentityType.SYSTEM)
        authorization_manager.register_identity(ident)
        return GuardianStatus.PASS, "Authorization system operational"
    except Exception as e:
        return GuardianStatus.FAIL, f"Authorization check failed: {e}"


def _check_audit_logging() -> tuple[GuardianStatus, str]:
    """Check audit logging."""
    try:
        from agent.guardian.audit import audit_log, AuditEvent, query_audit_log
        audit_log(AuditEvent.SECURITY_CHECK_PASSED, who="guardian-verify", what="verification audit test")
        entries = query_audit_log(event=AuditEvent.SECURITY_CHECK_PASSED, limit=1)
        if entries:
            return GuardianStatus.PASS, "Audit logging operational"
        return GuardianStatus.BLOCKED, "Audit log write succeeded but read returned no entries"
    except Exception as e:
        return GuardianStatus.FAIL, f"Audit logging check failed: {e}"


# ── Main verification runner ──────────────────────────────────────────


def run_guardian_verification() -> GuardianVerificationResult:
    """Run a complete Guardian verification across all subsystems.

    Returns:
        GuardianVerificationResult with PASS/BLOCKED/FAIL/DEFERRED per subsystem.
    """
    result = GuardianVerificationResult()

    checks = [
        ("CORE", _check_python_runtime),
        ("CORE", _check_imports),
        ("CORE", _check_configuration),
        ("CORE", _check_environment),
        ("CORE", _check_dependency_health),
        ("HERMES", _check_guardian_security),
        ("SECURITY", _check_emergency_stop),
        ("SECURITY", _check_authorization),
        ("SECURITY", _check_audit_logging),
        ("STORAGE", _check_guardian_storage),
        ("STORAGE", _check_guardian_recovery),
        ("TRADING", _check_trading),
        ("CRYPTO", _check_crypto),
        ("LEADGEN", _check_leadgen),
        ("MEDIA", _check_media),
    ]

    for subsystem, check_fn in checks:
        try:
            status, detail = check_fn()
            result.subsystem_statuses[subsystem] = status
            result.tests_run += 1
            if status == GuardianStatus.PASS:
                result.tests_passed += 1
            elif status == GuardianStatus.BLOCKED:
                result.tests_blocked += 1
                result.blocked_dependencies.append({
                    "subsystem": subsystem,
                    "reason": detail,
                })
            elif status == GuardianStatus.FAIL:
                result.tests_failed += 1
                result.failures.append({
                    "subsystem": subsystem,
                    "reason": detail,
                })
        except Exception as e:
            result.subsystem_statuses[subsystem] = GuardianStatus.FAIL
            result.tests_failed += 1
            result.failures.append({
                "subsystem": subsystem,
                "reason": f"Check threw exception: {e}",
            })

    # Determine overall status
    if result.tests_failed > 0:
        result.overall = GuardianStatus.FAIL
    elif result.tests_blocked > 0:
        result.overall = GuardianStatus.BLOCKED
    else:
        result.overall = GuardianStatus.PASS

    # Security lock state
    try:
        from agent.guardian.emergency import emergency_stop
        result.security_lock_state = {
            "global_stops": emergency_stop.get_all_stops(),
            "is_emergency_engaged": any(
                v == "halt" for v in emergency_stop.get_all_stops().values()
            ),
        }
    except Exception:
        result.security_lock_state = {"error": "Could not retrieve emergency stop state"}

    # Recommended next action
    if result.overall == GuardianStatus.PASS:
        result.recommended_next_action = "All systems operational. Proceed with autonomous work."
    elif result.overall == GuardianStatus.BLOCKED:
        result.recommended_next_action = "Resolve blocked dependencies before proceeding. Review blocked dependencies above."
    elif result.overall == GuardianStatus.FAIL:
        result.recommended_next_action = "Fix failures before proceeding. Review failure details above."

    return result


def format_human_readable(result: GuardianVerificationResult) -> str:
    """Format verification result for human-readable console output."""
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("GUARDIAN VERIFICATION REPORT")
    lines.append(f"Timestamp: {result.timestamp}")
    lines.append(f"Overall: {result.overall.value}")
    lines.append("=" * 60)
    lines.append("")

    # Subsystem statuses
    lines.append("SUBSYSTEM STATUS:")
    for subsystem, status in sorted(result.subsystem_statuses.items()):
        icon = "✓" if status == GuardianStatus.PASS else "✗" if status in (GuardianStatus.FAIL,) else "◷"
        lines.append(f"  {icon} {subsystem}: {status.value}")

    lines.append("")
    lines.append(f"Tests: {result.tests_run} total | {result.tests_passed} passed | {result.tests_failed} failed | {result.tests_blocked} blocked")
    lines.append("")

    # Blocked dependencies
    if result.blocked_dependencies:
        lines.append("BLOCKED DEPENDENCIES:")
        for dep in result.blocked_dependencies:
            lines.append(f"  • {dep['subsystem']}: {dep['reason']}")
        lines.append("")

    # Failures
    if result.failures:
        lines.append("FAILURES:")
        for fail in result.failures:
            lines.append(f"  • {fail['subsystem']}: {fail['reason']}")
        lines.append("")

    # Security lock state
    lines.append("SECURITY LOCK STATE:")
    for key, val in result.security_lock_state.items():
        lines.append(f"  {key}: {val}")
    lines.append("")

    lines.append(f"RECOMMENDED ACTION: {result.recommended_next_action}")
    lines.append("=" * 60)

    return "\n".join(lines)


# ── CLI parser ────────────────────────────────────────────────────────


def build_guardian_parser(subparsers, *, cmd_guardian: Callable) -> None:
    """Attach the ``guardian`` subcommand to ``subparsers``."""
    guardian_parser = subparsers.add_parser(
        "guardian",
        help="Guardian system verification and control",
        description="Verify, monitor, and control the Guardian autonomous operating system",
    )
    guardian_subparsers = guardian_parser.add_subparsers(dest="guardian_command")

    # guardian verify
    verify_parser = guardian_subparsers.add_parser(
        "verify",
        help="Run complete Guardian verification across all subsystems",
        description="Execute all relevant health checks and produce PASS/BLOCKED/FAIL/DEFERRED results",
    )
    verify_parser.add_argument(
        "--json", action="store_true",
        help="Emit machine-readable JSON report",
    )
    verify_parser.add_argument(
        "--timeout", type=int, default=120,
        help="Maximum seconds to run verification (default: 120)",
    )
    verify_parser.set_defaults(func=cmd_guardian)

    # guardian status
    status_parser = guardian_subparsers.add_parser(
        "status",
        help="Show Guardian subsystem status",
        description="Display current status of all Guardian subsystems",
    )
    status_parser.add_argument(
        "--json", action="store_true",
        help="Emit machine-readable JSON",
    )
    status_parser.set_defaults(func=cmd_guardian)

    # guardian health
    health_parser = guardian_subparsers.add_parser(
        "health",
        help="Run system health checks",
        description="Check core, Hermes, security, storage, trading, crypto, media, LEADGEN health",
    )
    health_parser.add_argument(
        "--json", action="store_true",
        help="Emit machine-readable JSON",
    )
    health_parser.set_defaults(func=cmd_guardian)

    # guardian e2e
    e2e_parser = guardian_subparsers.add_parser(
        "e2e",
        help="Run synthetic end-to-end mission proof",
        description="Execute a safe synthetic mission through the full Guardian pipeline",
    )
    e2e_parser.add_argument(
        "--json", action="store_true",
        help="Emit machine-readable JSON",
    )
    e2e_parser.set_defaults(func=cmd_guardian)

    guardian_parser.set_defaults(func=cmd_guardian)


# ── Handler functions ─────────────────────────────────────────────────


def cmd_guardian(args: argparse.Namespace) -> None:
    """Handle hermes guardian <subcommand>."""
    command = getattr(args, "guardian_command", None)

    if command == "verify" or command is None:
        result = run_guardian_verification()
        if getattr(args, "json", False):
            print(result.to_json())
        else:
            print(format_human_readable(result))
        # Exit code
        if result.overall == GuardianStatus.FAIL:
            sys.exit(1)
        elif result.overall == GuardianStatus.BLOCKED:
            sys.exit(2)
        else:
            sys.exit(0)

    elif command == "status":
        try:
            from agent.guardian.emergency import emergency_stop
            from agent.guardian.authorization import authorization_manager
            from hermes_cli.guardian_storage import check_disk_capacity
            from hermes_cli.guardian_storage import StorageLevel

            capacity = check_disk_capacity()
            stops = emergency_stop.get_all_stops()

            status_data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "storage": {
                    "level": capacity.level.value,
                    "free_gb": capacity.free_gb,
                    "total_gb": capacity.total_gb,
                    "used_percent": capacity.used_percent,
                },
                "emergency_stops": stops,
                "hermes_home": str(__import__("hermes_constants").get_hermes_home()),
            }

            if getattr(args, "json", False):
                print(json.dumps(status_data, indent=2))
            else:
                print(f"Guardian Status")
                print(f"  Storage: {capacity.level.value} ({capacity.free_gb:.1f} GB free)")
                print(f"  Emergency Stops: {len(stops)} active")
                for scope, level in stops.items():
                    print(f"    {scope}: {level}")

        except Exception as e:
            print(f"Status check failed: {e}")
            sys.exit(1)

    elif command == "health":
        try:
            result = run_guardian_verification()
            if getattr(args, "json", False):
                print(result.to_json())
            else:
                print(format_human_readable(result))
        except Exception as e:
            print(f"Health check failed: {e}")
            sys.exit(1)

    elif command == "e2e":
        try:
            from hermes_cli.guardian_e2e import run_synthetic_mission
            mission_result = run_synthetic_mission()
            if getattr(args, "json", False):
                print(json.dumps(mission_result, indent=2))
            else:
                print(f"End-to-End Mission: {mission_result.get('status', 'UNKNOWN')}")
                print(f"Steps completed: {mission_result.get('steps_completed', 0)}")
                print(f"Audit records: {mission_result.get('audit_records', 0)}")
        except ImportError:
            print("End-to-end module not yet available")
            sys.exit(1)
        except Exception as e:
            print(f"E2E mission failed: {e}")
            sys.exit(1)
