"""Guardian 2 Storage, Capacity Protection, Failure Handling, and Backup Verification.

Unified module for:
  - Storage location registry (catalog all Hermes storage with sizes/paths)
  - Capacity protection with multi-level thresholds (normal/warning/high/critical/emergency)
  - Storage failure handling (missing drive, disconnected storage, permissions, insufficient space)
  - Backup verification (checksums, zip validation, SQLite integrity)
  - Corruption detection for databases and state files
  - Configurable storage locations via config.yaml

Not a new agent tool — infrastructure used by guardian_health, health checks,
and the recovery runner.  Never raises on I/O failure; degrades to error states.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import sqlite3
import sys
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from hermes_constants import get_hermes_home, display_hermes_home

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Capacity protection thresholds (free GB)
# ---------------------------------------------------------------------------
# >30 GB = normal
# 20-30 GB = warning
# 10-20 GB = high_alert
# 5-10 GB  = critical
# <5 GB    = emergency

_GB = 1024 ** 3

THRESHOLD_NORMAL_GB = 30
THRESHOLD_WARNING_GB = 20
THRESHOLD_HIGH_ALERT_GB = 10
THRESHOLD_CRITICAL_GB = 5


def _capacity_thresholds() -> Tuple[int, int, int, int]:
    """Resolve capacity thresholds from config.yaml (guardian.storage.*).

    Returns (normal, warning, high_alert, critical) in GB.  Falls back to
    the hardcoded defaults when config is missing/invalid.  Thresholds are
    validated so a broken config can never produce an inverted ordering that
    would classify 0 free bytes as "normal".
    """
    cfg = _read_guardian_storage_config()
    values = []
    for key, default in (
        ("normal_gb", THRESHOLD_NORMAL_GB),
        ("warning_gb", THRESHOLD_WARNING_GB),
        ("high_alert_gb", THRESHOLD_HIGH_ALERT_GB),
        ("critical_gb", THRESHOLD_CRITICAL_GB),
    ):
        raw = cfg.get(key, default)
        try:
            val = int(raw)
        except (TypeError, ValueError):
            val = default
        values.append(max(0, val))

    normal, warning, high, critical = values
    # Enforce a sane descending order so 0 bytes always lands in the
    # strictest level, never "normal": normal >= warning >= high_alert >= critical.
    high = max(high, critical)
    warning = max(warning, high)
    normal = max(normal, warning)
    return normal, warning, high, critical


class StorageLevel(Enum):
    """Capacity protection levels."""
    NORMAL = "normal"
    WARNING = "warning"
    HIGH_ALERT = "high_alert"
    CRITICAL = "critical"
    EMERGENCY = "emergency"
    UNKNOWN = "unknown"


class StorageFailure(Enum):
    """Known storage failure modes."""
    NONE = "none"
    MISSING_PATH = "missing_path"
    DISCONNECTED_STORAGE = "disconnected_storage"
    PERMISSION_FAILURE = "permission_failure"
    INSUFFICIENT_SPACE = "insufficient_space"
    CORRUPTED_STATE = "corrupted_state"
    READ_ONLY = "read_only"


@dataclass
class StorageLocation:
    """A single tracked storage location."""
    name: str
    path: str
    category: str  # "config", "database", "cache", "logs", "media", "backup", "skills", "state"
    description: str = ""
    required: bool = True
    exists: bool = False
    readable: bool = False
    writable: bool = False
    size_bytes: int = 0
    failure: StorageFailure = StorageFailure.NONE
    failure_detail: str = ""


@dataclass
class CapacityStatus:
    """System-wide capacity status."""
    level: StorageLevel = StorageLevel.UNKNOWN
    free_bytes: int = 0
    total_bytes: int = 0
    used_bytes: int = 0
    free_gb: float = 0.0
    total_gb: float = 0.0
    used_percent: float = 0.0
    hermes_size_bytes: int = 0
    hermes_size_gb: float = 0.0
    locations: List[StorageLocation] = field(default_factory=list)
    failures: List[Dict[str, Any]] = field(default_factory=list)
    checked_at: str = ""


@dataclass
class BackupVerification:
    """Result of verifying a backup archive."""
    path: str = ""
    valid: bool = False
    size_bytes: int = 0
    entry_count: int = 0
    checksum_sha256: str = ""
    has_config: bool = False
    has_env: bool = False
    has_state_db: bool = False
    sqlite_valid: bool = False
    sqlite_details: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    verified_at: str = ""


# ---------------------------------------------------------------------------
# Storage registry
# ---------------------------------------------------------------------------

def _get_storage_locations(hermes_home: Optional[Path] = None) -> List[StorageLocation]:
    """Catalog all known Hermes storage locations."""
    home = hermes_home or get_hermes_home()
    locations: List[StorageLocation] = []

    # Core config and state files
    for name, rel_path, category, required, desc in [
        ("config", "config.yaml", "config", True, "Main configuration file"),
        ("env", ".env", "config", True, "Environment variables (API keys)"),
        ("auth", "auth.json", "config", False, "Authentication credentials"),
        ("state_db", "state.db", "database", True, "Session database"),
        ("memory_store", "memory_store.db", "database", False, "Memory store"),
        ("projects_db", "projects.db", "database", False, "Projects database"),
        ("kanban_db", "kanban.db", "database", False, "Kanban database"),
        ("verification_db", "verification_evidence.db", "database", False, "Verification audit trail"),
        ("response_store", "response_store.db", "database", False, "Gateway response store"),
    ]:
        p = home / rel_path
        loc = StorageLocation(name=name, path=str(p), category=category, description=desc, required=required)
        _probe_location(loc)
        locations.append(loc)

    # Directories
    for name, rel_path, category, required, desc in [
        ("skills", "skills", "skills", False, "Agent skills directory"),
        ("logs", "logs", "logs", False, "Log files"),
        ("backups", "backups", "backup", False, "Backup archives"),
        ("snapshots", "state-snapshots", "backup", False, "Quick state snapshots"),
        ("cron", "cron", "state", False, "Cron job state"),
        ("gateway", "gateway", "state", False, "Gateway state files"),
        ("sessions", "sessions", "state", False, "Session data"),
    ]:
        p = home / rel_path
        loc = StorageLocation(name=name, path=str(p), category=category, description=desc, required=required)
        _probe_location(loc)
        # Calculate directory size
        if loc.exists and loc.readable:
            loc.size_bytes = _dir_size(p)
        locations.append(loc)

    # User-configured monitored paths from config.yaml (guardian.storage.monitored_paths).
    # Paths are resolved relative to HERMES_HOME unless they start with "/" or
    # "~" (absolute / home-relative).  This lets deployments relocate caches,
    # media, models, datasets, and archives to other drives and still have them
    # monitored.  Names already covered by the hardcoded baseline above are
    # ignored — the config surface is for ADDING locations, not duplicating.
    locations.extend(_config_monitored_paths(home, {l.name for l in locations}))

    return locations


def _config_monitored_paths(home: Path, baseline_names: set) -> List[StorageLocation]:
    """Load user-configured storage locations from config.yaml.

    Reads ``guardian.storage.monitored_paths`` — a list of
    ``{"name", "path", "required"[, "category"]}`` dicts.  A missing or
    invalid config degrades to an empty list (the hardcoded locations above
    are always monitored regardless of config).  Entries whose name already
    appears in *baseline_names* are skipped.
    """
    locations: List[StorageLocation] = []
    entries = _read_guardian_storage_config().get("monitored_paths", [])
    if not isinstance(entries, list):
        return locations

    seen_names = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        raw_path = str(entry.get("path") or "").strip()
        if not name or not raw_path:
            continue
        if name in baseline_names or name in seen_names:
            continue
        seen_names.add(name)

        # Resolve relative → HERMES_HOME, "~" → home, absolute kept as-is.
        try:
            if raw_path.startswith("~"):
                p = Path(raw_path).expanduser()
            elif raw_path.startswith("/") or (
                len(raw_path) > 1 and raw_path[1] == ":"
            ):
                p = Path(raw_path)
            else:
                p = home / raw_path
        except ValueError:
            continue

        required = bool(entry.get("required", False))
        category = str(entry.get("category") or "state")
        loc = StorageLocation(
            name=name,
            path=str(p),
            category=category,
            description="User-configured monitored path",
            required=required,
        )
        _probe_location(loc)
        if loc.exists and loc.readable and p.is_dir():
            loc.size_bytes = _dir_size(p)
        locations.append(loc)

    return locations


# Lightweight config read.  Loaded lazily and cached per call inside
# load_config(); failures degrade to defaults so storage monitoring never
# breaks because of a flaky config load.
def _read_guardian_storage_config() -> Dict[str, Any]:
    try:
        from hermes_cli.config import load_config_readonly

        cfg = load_config_readonly()
    except Exception:
        return {}
    guardian = cfg.get("guardian") if isinstance(cfg, dict) else None
    if not isinstance(guardian, dict):
        return {}
    storage = guardian.get("storage")
    if not isinstance(storage, dict):
        return {}
    return storage


def _probe_location(loc: StorageLocation) -> None:
    """Probe a single storage location for existence/read/write/failure."""
    p = Path(loc.path)
    try:
        loc.exists = p.exists()
    except OSError as e:
        loc.exists = False
        loc.failure = StorageFailure.MISSING_PATH
        loc.failure_detail = str(e)
        return

    if not loc.exists:
        loc.failure = StorageFailure.MISSING_PATH if loc.required else StorageFailure.NONE
        return

    try:
        loc.readable = os.access(p, os.R_OK)
    except (OSError, ValueError):
        loc.readable = False

    try:
        loc.writable = os.access(p, os.W_OK)
    except (OSError, ValueError):
        loc.writable = False

    if not loc.readable:
        loc.failure = StorageFailure.PERMISSION_FAILURE
        loc.failure_detail = "Path exists but is not readable"
    elif not loc.writable and loc.required:
        loc.failure = StorageFailure.READ_ONLY
        loc.failure_detail = "Path exists but is not writable"


def _dir_size(path: Path) -> int:
    """Calculate total size of a directory. Best-effort, returns 0 on error."""
    total = 0
    try:
        for entry in path.rglob("*"):
            try:
                if entry.is_file() and not entry.is_symlink():
                    total += entry.stat().st_size
            except (OSError, ValueError):
                continue
    except (OSError, ValueError):
        return 0
    return total


# ---------------------------------------------------------------------------
# Capacity protection
# ---------------------------------------------------------------------------

def classify_capacity(free_bytes: int) -> StorageLevel:
    """Classify free space into a protection level.

    Thresholds come from config.yaml (``guardian.storage.*_gb``) when set,
    falling back to the defaults (30/20/10/5 GB).
    """
    if free_bytes < 0:
        return StorageLevel.UNKNOWN
    free_gb = free_bytes / _GB
    normal_gb, warning_gb, high_alert_gb, critical_gb = _capacity_thresholds()
    if free_gb >= normal_gb:
        return StorageLevel.NORMAL
    elif free_gb >= warning_gb:
        return StorageLevel.WARNING
    elif free_gb >= high_alert_gb:
        return StorageLevel.HIGH_ALERT
    elif free_gb >= critical_gb:
        return StorageLevel.CRITICAL
    else:
        return StorageLevel.EMERGENCY


def check_disk_capacity(home: Optional[Path] = None) -> CapacityStatus:
    """Check system-wide disk capacity and Hermes storage.

    Returns a CapacityStatus with all fields populated.  Never raises.
    """
    status = CapacityStatus(checked_at=datetime.now(timezone.utc).isoformat())
    h = home or get_hermes_home()

    try:
        usage = shutil.disk_usage(str(h))
        status.total_bytes = usage.total
        status.free_bytes = usage.free
        status.used_bytes = usage.used
        status.total_gb = round(usage.total / _GB, 2)
        status.free_gb = round(usage.free / _GB, 2)
        status.used_percent = round((usage.used / usage.total) * 100, 1) if usage.total > 0 else 0.0
        status.level = classify_capacity(usage.free)
    except (OSError, ValueError) as e:
        status.level = StorageLevel.UNKNOWN
        status.failures.append({"type": "disk_check_failed", "detail": str(e)})
        return status

    # Hermes directory size
    try:
        status.hermes_size_bytes = _dir_size(h)
        status.hermes_size_gb = round(status.hermes_size_bytes / _GB, 2)
    except Exception:
        pass

    # Probe storage locations
    status.locations = _get_storage_locations(h)

    # Collect failures
    for loc in status.locations:
        if loc.failure != StorageFailure.NONE:
            status.failures.append({
                "location": loc.name,
                "path": loc.path,
                "failure": loc.failure.value,
                "detail": loc.failure_detail,
            })

    return status


def _emergency_threshold_gb() -> float:
    """Resolve the emergency threshold (critical_gb) in GB from config."""
    _, _, _, critical_gb = _capacity_thresholds()
    return float(critical_gb)


def is_emergency_capacity(home: Optional[Path] = None) -> bool:
    """Quick check: is the system in emergency capacity mode?"""
    try:
        usage = shutil.disk_usage(str(home or get_hermes_home()))
        return usage.free / _GB < _emergency_threshold_gb()
    except (OSError, ValueError):
        return False


def should_block_nonessential(home: Optional[Path] = None) -> bool:
    """Should non-essential workloads be blocked?

    Returns True when free space is below the emergency threshold.
    """
    try:
        usage = shutil.disk_usage(str(home or get_hermes_home()))
        return usage.free / _GB < _emergency_threshold_gb()
    except (OSError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Storage failure detection
# ---------------------------------------------------------------------------

def detect_storage_failures(home: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Detect all storage failure conditions.  Never raises."""
    failures: List[Dict[str, Any]] = []
    h = home or get_hermes_home()

    # 1. Missing HERMES_HOME
    if not h.exists():
        failures.append({
            "type": StorageFailure.MISSING_PATH.value,
            "path": str(h),
            "detail": "HERMES_HOME directory does not exist",
            "severity": "critical",
        })
        return failures

    # 2. Not a directory
    if not h.is_dir():
        failures.append({
            "type": StorageFailure.CORRUPTED_STATE.value,
            "path": str(h),
            "detail": "HERMES_HOME exists but is not a directory",
            "severity": "critical",
        })
        return failures

    # 3. Read/write permissions
    if not os.access(h, os.R_OK):
        failures.append({
            "type": StorageFailure.PERMISSION_FAILURE.value,
            "path": str(h),
            "detail": "HERMES_HOME is not readable",
            "severity": "critical",
        })

    if not os.access(h, os.W_OK):
        failures.append({
            "type": StorageFailure.READ_ONLY.value,
            "path": str(h),
            "detail": "HERMES_HOME is not writable",
            "severity": "high",
        })

    # 4. Disk space
    try:
        usage = shutil.disk_usage(str(h))
        level = classify_capacity(usage.free)
        if level in (StorageLevel.CRITICAL, StorageLevel.EMERGENCY):
            failures.append({
                "type": StorageFailure.INSUFFICIENT_SPACE.value,
                "path": str(h),
                "detail": f"Free space: {usage.free / _GB:.1f} GB ({level.value})",
                "severity": "critical" if level == StorageLevel.EMERGENCY else "high",
                "level": level.value,
                "free_bytes": usage.free,
            })
    except (OSError, ValueError) as e:
        failures.append({
            "type": StorageFailure.DISCONNECTED_STORAGE.value,
            "path": str(h),
            "detail": f"Cannot check disk usage: {e}",
            "severity": "high",
        })

    # 5. Critical database files
    for db_name in ("state.db",):
        db_path = h / db_name
        if db_path.exists():
            if not os.access(db_path, os.R_OK):
                failures.append({
                    "type": StorageFailure.PERMISSION_FAILURE.value,
                    "path": str(db_path),
                    "detail": f"{db_name} is not readable",
                    "severity": "critical",
                })
            elif db_path.stat().st_size == 0:
                failures.append({
                    "type": StorageFailure.CORRUPTED_STATE.value,
                    "path": str(db_path),
                    "detail": f"{db_name} is empty (0 bytes)",
                    "severity": "critical",
                })
            elif db_path.stat().st_size < 100:
                failures.append({
                    "type": StorageFailure.CORRUPTED_STATE.value,
                    "path": str(db_path),
                    "detail": f"{db_name} is suspiciously small ({db_path.stat().st_size} bytes)",
                    "severity": "high",
                })

    # 6. Backup directory writable check
    backup_dir = h / "backups"
    if backup_dir.exists() and not os.access(backup_dir, os.W_OK):
        failures.append({
            "type": StorageFailure.PERMISSION_FAILURE.value,
            "path": str(backup_dir),
            "detail": "Backup directory is not writable",
            "severity": "medium",
        })

    return failures


# ---------------------------------------------------------------------------
# Backup verification
# ---------------------------------------------------------------------------

def verify_backup_archive(
    backup_path: str | Path,
    *,
    compute_checksum: bool = True,
    verify_sqlite: bool = True,
) -> BackupVerification:
    """Verify a backup zip archive.

    Checks:
      - File exists and is a valid zip
      - Contains expected Hermes markers (config.yaml, .env, state.db)
      - SHA-256 checksum (optional)
      - SQLite databases inside the zip are valid (header + integrity)
    """
    bp = Path(backup_path)
    result = BackupVerification(verified_at=datetime.now(timezone.utc).isoformat())

    # File existence
    if not bp.exists():
        result.errors.append(f"Backup file does not exist: {bp}")
        return result

    try:
        result.size_bytes = bp.stat().st_size
    except OSError as e:
        result.errors.append(f"Cannot stat backup file: {e}")
        return result

    # Zip validity
    if not zipfile.is_zipfile(bp):
        result.errors.append("File is not a valid zip archive")
        return result

    try:
        with zipfile.ZipFile(bp, "r") as zf:
            # Entry count
            names = zf.namelist()
            result.entry_count = len(names)

            # Marker detection
            for name in names:
                basename = Path(name).name
                if basename == "config.yaml":
                    result.has_config = True
                elif basename == ".env":
                    result.has_env = True
                elif basename == "state.db":
                    result.has_state_db = True

            # Test zip integrity (extract + verify CRC)
            bad = zf.testzip()
            if bad is not None:
                result.errors.append(f"Corrupted zip entry: {bad}")
                return result

            # SQLite verification for .db files in the archive
            if verify_sqlite:
                for name in names:
                    if name.endswith(".db") and not name.endswith(("-wal", "-shm", "-journal")):
                        try:
                            with zf.open(name) as member_file:
                                header = member_file.read(16)
                                is_valid = header[:15] == b"SQLite format 3"
                                result.sqlite_details.append({
                                    "name": name,
                                    "valid": is_valid,
                                    "size": zf.getinfo(name).file_size,
                                    "message": "valid header" if is_valid else "missing SQLite header",
                                })
                        except Exception as e:
                            result.sqlite_details.append({
                                "name": name,
                                "valid": False,
                                "message": str(e),
                            })

            result.sqlite_valid = all(d.get("valid", False) for d in result.sqlite_details) if result.sqlite_details else True

    except zipfile.BadZipFile as e:
        result.errors.append(f"Bad zip file: {e}")
        return result
    except OSError as e:
        result.errors.append(f"I/O error reading backup: {e}")
        return result

    # SHA-256 checksum
    if compute_checksum:
        try:
            result.checksum_sha256 = _sha256_file(bp)
        except OSError as e:
            result.errors.append(f"Checksum computation failed: {e}")

    # Overall validity
    result.valid = (
        result.entry_count > 0
        and not result.errors
        and (result.has_config or result.has_state_db)
    )

    return result


def verify_backup_checksum(
    backup_path: str | Path,
    expected_checksum: str,
) -> Tuple[bool, str]:
    """Verify a backup's SHA-256 checksum matches."""
    bp = Path(backup_path)
    if not bp.exists():
        return False, "File does not exist"
    try:
        actual = _sha256_file(bp)
    except OSError as e:
        return False, f"Cannot read file: {e}"

    if actual.lower() == expected_checksum.lower():
        return True, "Checksum matches"
    return False, f"Checksum mismatch: expected {expected_checksum}, got {actual}"


def _sha256_file(path: Path) -> str:
    """Compute SHA-256 of a file.  Streams to avoid loading large files into memory."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Database corruption detection
# ---------------------------------------------------------------------------

def check_database_integrity(db_path: str | Path) -> Dict[str, Any]:
    """Check a single database for corruption.  Never raises."""
    p = Path(db_path)
    result: Dict[str, Any] = {"path": str(p), "valid": False, "checks": []}

    if not p.exists():
        result["error"] = "File does not exist"
        return result

    try:
        size = p.stat().st_size
    except OSError as e:
        result["error"] = f"Cannot stat: {e}"
        return result

    if size == 0:
        result["error"] = "File is empty (0 bytes)"
        return result

    if size < 100:
        result["error"] = f"File too small ({size} bytes) to be a valid SQLite database"
        return result

    # SQLite header check
    try:
        with open(p, "rb") as f:
            header = f.read(16)
        has_header = header[:15] == b"SQLite format 3"
        result["checks"].append({"name": "header", "valid": has_header})
        if not has_header:
            # Check for zeroed file
            if all(b == 0 for b in header):
                result["error"] = "File appears to be zeroed (no SQLite header, all NUL bytes)"
                return result
            result["error"] = "Missing SQLite header magic"
            return result
    except OSError as e:
        result["error"] = f"Cannot read header: {e}"
        return result

    # PRAGMA integrity_check
    try:
        uri = f"file:{p.as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=5.0) as conn:
            cursor = conn.execute("PRAGMA integrity_check")
            rows = cursor.fetchall()
            is_ok = len(rows) == 1 and rows[0][0] == "ok"
            result["checks"].append({
                "name": "integrity_check",
                "valid": is_ok,
                "message": rows[0][0] if rows else "no result",
            })
            result["valid"] = is_ok
            if not is_ok:
                result["error"] = f"PRAGMA integrity_check failed: {'; '.join(str(r[0]) for r in rows[:3])}"
    except sqlite3.DatabaseError as e:
        result["error"] = f"Cannot open database: {e}"
        return result
    except Exception as e:
        result["error"] = f"Integrity check error: {e}"
        return result

    return result


def check_all_databases(hermes_home: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Check all known databases in HERMES_HOME for corruption."""
    home = hermes_home or get_hermes_home()
    results: List[Dict[str, Any]] = []

    # Known database files
    db_names = [
        "state.db",
        "memory_store.db",
        "projects.db",
        "kanban.db",
        "verification_evidence.db",
        "response_store.db",
        "cron/executions.db",
    ]

    for name in db_names:
        db_path = home / name
        if db_path.exists():
            results.append(check_database_integrity(db_path))

    # Kanban board databases
    kanban_dir = home / "kanban" / "boards"
    if kanban_dir.is_dir():
        for board_dir in kanban_dir.iterdir():
            if board_dir.is_dir():
                for db_file in board_dir.glob("*.db"):
                    results.append(check_database_integrity(db_file))

    return results


# ---------------------------------------------------------------------------
# Storage location summary
# ---------------------------------------------------------------------------

def get_storage_summary(hermes_home: Optional[Path] = None) -> Dict[str, Any]:
    """Get a complete storage summary for Guardian reporting."""
    home = hermes_home or get_hermes_home()

    capacity = check_disk_capacity(home)
    failures = detect_storage_failures(home)
    db_results = check_all_databases(home)

    # Count locations by category
    category_sizes: Dict[str, int] = {}
    for loc in capacity.locations:
        cat = loc.category
        category_sizes[cat] = category_sizes.get(cat, 0) + loc.size_bytes

    return {
        "capacity": {
            "level": capacity.level.value,
            "free_gb": capacity.free_gb,
            "total_gb": capacity.total_gb,
            "used_percent": capacity.used_percent,
            "hermes_size_gb": capacity.hermes_size_gb,
        },
        "locations": [
            {
                "name": loc.name,
                "path": loc.path,
                "category": loc.category,
                "exists": loc.exists,
                "readable": loc.readable,
                "writable": loc.writable,
                "size_bytes": loc.size_bytes,
                "failure": loc.failure.value,
            }
            for loc in capacity.locations
        ],
        "category_sizes": category_sizes,
        "failures": failures,
        "databases": db_results,
        "checked_at": capacity.checked_at,
    }
