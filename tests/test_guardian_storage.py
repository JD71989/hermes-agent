"""Tests for guardian_storage.py — Guardian 2 Storage, Capacity, and Verification.

Covers:
  1. Normal storage
  2. Low storage (threshold classification)
  3. Disconnected storage (missing path)
  4. Missing storage (non-existent HERMES_HOME)
  5. Failed backup (invalid zip, missing files)
  6. Invalid backup (corrupted, empty)
  7. Successful backup verification
  8. Database corruption detection
  9. Storage location registry
"""

import json
import os
import sqlite3
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def hermes_home(tmp_path):
    """Create a temporary HERMES_HOME with realistic structure."""
    home = tmp_path / ".hermes"
    home.mkdir()

    # Config
    (home / "config.yaml").write_text("model:\n  provider: test\n", encoding="utf-8")
    (home / ".env").write_text("TEST_KEY=test-value\n", encoding="utf-8")

    # Databases
    for db_name in ("state.db", "memory_store.db"):
        with sqlite3.connect(str(home / db_name)) as conn:
            conn.execute("CREATE TABLE t (v TEXT)")
            conn.execute("INSERT INTO t VALUES ('ok')")
            conn.commit()

    # Skills
    skills_dir = home / "skills" / "test-skill"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text("# Test\n", encoding="utf-8")

    # Backups dir
    (home / "backups").mkdir()

    # Logs
    logs_dir = home / "logs"
    logs_dir.mkdir()
    (logs_dir / "agent.log").write_text("log entry\n", encoding="utf-8")

    return home


@pytest.fixture
def backup_zip(tmp_path, hermes_home):
    """Create a valid backup zip."""
    out = tmp_path / "test-backup.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("config.yaml", "model:\n  provider: openrouter\n")
        zf.writestr(".env", "API_KEY=sk-test\n")
        # SQLite DB
        db_path = hermes_home / "state.db"
        zf.write(db_path, "state.db")
    return out


@pytest.fixture
def corrupted_backup_zip(tmp_path):
    """Create a corrupted backup zip."""
    out = tmp_path / "corrupted-backup.zip"
    with open(out, "wb") as f:
        f.write(b"PK\x03\x04NOT_A_REAL_ZIP")
    return out


@pytest.fixture
def empty_backup_zip(tmp_path):
    """Create an empty backup zip."""
    out = tmp_path / "empty-backup.zip"
    with zipfile.ZipFile(out, "w") as zf:
        pass  # empty
    return out


@pytest.fixture
def invalid_backup_zip(tmp_path):
    """Create a backup zip with no Hermes markers."""
    out = tmp_path / "invalid-backup.zip"
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("random_file.txt", "not a hermes backup")
    return out


@pytest.fixture
def valid_backup_with_db(tmp_path):
    """Create a backup with a valid SQLite database."""
    out = tmp_path / "valid-db-backup.zip"
    # Create a valid SQLite DB
    db_path = tmp_path / "test_state.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("CREATE TABLE sessions (id INTEGER PRIMARY KEY, data TEXT)")
        conn.execute("INSERT INTO sessions (data) VALUES ('test_session')")
        conn.commit()

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("config.yaml", "model:\n  provider: test\n")
        zf.writestr(".env", "KEY=VAL\n")
        zf.write(db_path, "state.db")
    return out


# ---------------------------------------------------------------------------
# 1. Normal storage — capacity classification
# ---------------------------------------------------------------------------

class TestCapacityClassification:
    """Test that free space maps to correct protection levels."""

    def test_normal_above_30gb(self):
        from hermes_cli.guardian_storage import classify_capacity, StorageLevel, _GB
        level = classify_capacity(int(50 * _GB))
        assert level == StorageLevel.NORMAL

    def test_warning_20_to_30gb(self):
        from hermes_cli.guardian_storage import classify_capacity, StorageLevel, _GB
        level = classify_capacity(int(25 * _GB))
        assert level == StorageLevel.WARNING

    def test_high_alert_10_to_20gb(self):
        from hermes_cli.guardian_storage import classify_capacity, StorageLevel, _GB
        level = classify_capacity(int(15 * _GB))
        assert level == StorageLevel.HIGH_ALERT

    def test_critical_5_to_10gb(self):
        from hermes_cli.guardian_storage import classify_capacity, StorageLevel, _GB
        level = classify_capacity(int(7 * _GB))
        assert level == StorageLevel.CRITICAL

    def test_emergency_below_5gb(self):
        from hermes_cli.guardian_storage import classify_capacity, StorageLevel, _GB
        level = classify_capacity(int(3 * _GB))
        assert level == StorageLevel.EMERGENCY

    def test_negative_returns_unknown(self):
        from hermes_cli.guardian_storage import classify_capacity, StorageLevel
        level = classify_capacity(-1)
        assert level == StorageLevel.UNKNOWN

    def test_zero_is_emergency(self):
        from hermes_cli.guardian_storage import classify_capacity, StorageLevel
        level = classify_capacity(0)
        assert level == StorageLevel.EMERGENCY

    def test_boundary_30gb_is_normal(self):
        from hermes_cli.guardian_storage import classify_capacity, StorageLevel, _GB
        level = classify_capacity(int(30 * _GB))
        assert level == StorageLevel.NORMAL

    def test_boundary_20gb_is_warning(self):
        from hermes_cli.guardian_storage import classify_capacity, StorageLevel, _GB
        level = classify_capacity(int(20 * _GB))
        assert level == StorageLevel.WARNING

    def test_boundary_10gb_is_high_alert(self):
        from hermes_cli.guardian_storage import classify_capacity, StorageLevel, _GB
        level = classify_capacity(int(10 * _GB))
        assert level == StorageLevel.HIGH_ALERT

    def test_boundary_5gb_is_critical(self):
        from hermes_cli.guardian_storage import classify_capacity, StorageLevel, _GB
        level = classify_capacity(int(5 * _GB))
        assert level == StorageLevel.CRITICAL


# ---------------------------------------------------------------------------
# 2. Low storage — check_disk_capacity with mocked disk_usage
# ---------------------------------------------------------------------------

class TestDiskCapacity:
    """Test check_disk_capacity with mocked disk usage."""

    def test_returns_capacity_status(self, hermes_home):
        from hermes_cli.guardian_storage import check_disk_capacity, StorageLevel

        # Mock disk usage to simulate a known state
        fake_usage = type("Usage", (), {"total": 100 * 1024**3, "free": 40 * 1024**3, "used": 60 * 1024**3})()
        with patch("hermes_cli.guardian_storage.shutil.disk_usage", return_value=fake_usage):
            status = check_disk_capacity(hermes_home)

        assert status.level == StorageLevel.NORMAL
        assert status.free_gb == 40.0
        assert status.total_gb == 100.0
        assert status.used_percent == 60.0

    def test_low_space_detected(self, hermes_home):
        from hermes_cli.guardian_storage import check_disk_capacity, StorageLevel

        fake_usage = type("Usage", (), {"total": 100 * 1024**3, "free": 3 * 1024**3, "used": 97 * 1024**3})()
        with patch("hermes_cli.guardian_storage.shutil.disk_usage", return_value=fake_usage):
            status = check_disk_capacity(hermes_home)

        assert status.level == StorageLevel.EMERGENCY
        assert status.free_gb == 3.0

    def test_disk_check_failure(self, hermes_home):
        from hermes_cli.guardian_storage import check_disk_capacity, StorageLevel

        with patch("hermes_cli.guardian_storage.shutil.disk_usage", side_effect=OSError("disk offline")):
            status = check_disk_capacity(hermes_home)

        assert status.level == StorageLevel.UNKNOWN
        assert len(status.failures) > 0

    def test_locations_populated(self, hermes_home):
        from hermes_cli.guardian_storage import check_disk_capacity

        status = check_disk_capacity(hermes_home)
        assert len(status.locations) > 0
        # At least config.yaml should exist
        config_locs = [l for l in status.locations if l.name == "config"]
        assert len(config_locs) == 1
        assert config_locs[0].exists is True
        assert config_locs[0].readable is True


# ---------------------------------------------------------------------------
# 3. Disconnected / missing storage
# ---------------------------------------------------------------------------

class TestStorageFailures:
    """Test storage failure detection."""

    def test_missing_hermes_home(self, tmp_path):
        from hermes_cli.guardian_storage import detect_storage_failures
        nonexistent = tmp_path / "nonexistent"
        failures = detect_storage_failures(nonexistent)
        assert any(f["type"] == "missing_path" for f in failures)

    def test_not_a_directory(self, tmp_path):
        from hermes_cli.guardian_storage import detect_storage_failures
        file_path = tmp_path / "not_a_dir"
        file_path.write_text("hello", encoding="utf-8")
        failures = detect_storage_failures(file_path)
        assert any(f["type"] == "corrupted_state" for f in failures)

    def test_read_only_directory(self, hermes_home):
        from hermes_cli.guardian_storage import detect_storage_failures
        # Make directory read-only (skip on Windows where this is less reliable)
        if os.name == "nt":
            pytest.skip("Permission test unreliable on Windows")
        original_mode = hermes_home.stat().st_mode
        try:
            hermes_home.chmod(0o555)
            failures = detect_storage_failures(hermes_home)
            # Should detect read-only
            assert any(f["type"] in ("read_only", "permission_failure") for f in failures)
        finally:
            hermes_home.chmod(original_mode)

    def test_empty_database_detected(self, hermes_home):
        from hermes_cli.guardian_storage import detect_storage_failures
        # Create an empty state.db
        db_path = hermes_home / "state.db"
        db_path.write_bytes(b"")
        failures = detect_storage_failures(hermes_home)
        assert any(
            f["type"] == "corrupted_state" and "empty" in f.get("detail", "").lower()
            for f in failures
        )

    def test_small_database_detected(self, hermes_home):
        from hermes_cli.guardian_storage import detect_storage_failures
        db_path = hermes_home / "state.db"
        db_path.write_bytes(b"x" * 50)  # Too small for valid SQLite
        failures = detect_storage_failures(hermes_home)
        assert any(
            f["type"] == "corrupted_state" and "small" in f.get("detail", "").lower()
            for f in failures
        )

    def test_low_disk_space_detected(self, hermes_home):
        from hermes_cli.guardian_storage import detect_storage_failures
        fake_usage = type("Usage", (), {"total": 100 * 1024**3, "free": 2 * 1024**3, "used": 98 * 1024**3})()
        with patch("hermes_cli.guardian_storage.shutil.disk_usage", return_value=fake_usage):
            failures = detect_storage_failures(hermes_home)
        assert any(f["type"] == "insufficient_space" for f in failures)


# ---------------------------------------------------------------------------
# 4. Backup verification — failed/invalid backups
# ---------------------------------------------------------------------------

class TestBackupVerificationFailure:
    """Test backup verification with bad inputs."""

    def test_nonexistent_backup(self, tmp_path):
        from hermes_cli.guardian_storage import verify_backup_archive
        result = verify_backup_archive(tmp_path / "nonexistent.zip")
        assert result.valid is False
        assert any("does not exist" in e for e in result.errors)

    def test_corrupted_backup(self, corrupted_backup_zip):
        from hermes_cli.guardian_storage import verify_backup_archive
        result = verify_backup_archive(corrupted_backup_zip)
        assert result.valid is False
        assert any("not a valid zip" in e.lower() or "bad zip" in e.lower() for e in result.errors)

    def test_empty_backup(self, empty_backup_zip):
        from hermes_cli.guardian_storage import verify_backup_archive
        result = verify_backup_archive(empty_backup_zip, compute_checksum=False)
        assert result.valid is False
        # Empty zip has 0 entries and no Hermes markers — fails validity
        assert result.entry_count == 0
        assert result.has_config is False
        assert result.has_state_db is False

    def test_invalid_backup_no_markers(self, invalid_backup_zip):
        from hermes_cli.guardian_storage import verify_backup_archive
        result = verify_backup_archive(invalid_backup_zip, compute_checksum=False)
        assert result.valid is False

    def test_non_zip_file(self, tmp_path):
        from hermes_cli.guardian_storage import verify_backup_archive
        not_zip = tmp_path / "not_a.zip"
        not_zip.write_text("hello world")
        result = verify_backup_archive(not_zip)
        assert result.valid is False
        assert any("not a valid zip" in e.lower() for e in result.errors)


# ---------------------------------------------------------------------------
# 5. Backup verification — successful
# ---------------------------------------------------------------------------

class TestBackupVerificationSuccess:
    """Test backup verification with valid backups."""

    def test_valid_backup(self, backup_zip):
        from hermes_cli.guardian_storage import verify_backup_archive
        result = verify_backup_archive(backup_zip)
        assert result.valid is True
        assert result.has_config is True
        assert result.entry_count > 0
        assert result.size_bytes > 0
        assert len(result.errors) == 0

    def test_checksum_computed(self, backup_zip):
        from hermes_cli.guardian_storage import verify_backup_archive
        result = verify_backup_archive(backup_zip, compute_checksum=True)
        assert result.checksum_sha256 != ""
        assert len(result.checksum_sha256) == 64  # SHA-256 hex

    def test_checksum_skip(self, backup_zip):
        from hermes_cli.guardian_storage import verify_backup_archive
        result = verify_backup_archive(backup_zip, compute_checksum=False)
        assert result.checksum_sha256 == ""

    def test_valid_backup_with_db(self, valid_backup_with_db):
        from hermes_cli.guardian_storage import verify_backup_archive
        result = verify_backup_archive(valid_backup_with_db, verify_sqlite=True)
        assert result.valid is True
        assert result.has_state_db is True
        assert result.sqlite_valid is True
        assert len(result.sqlite_details) > 0

    def test_checksum_matches(self, backup_zip):
        from hermes_cli.guardian_storage import verify_backup_archive, verify_backup_checksum
        result = verify_backup_archive(backup_zip, compute_checksum=True)
        ok, msg = verify_backup_checksum(backup_zip, result.checksum_sha256)
        assert ok is True

    def test_checksum_mismatch(self, backup_zip):
        from hermes_cli.guardian_storage import verify_backup_checksum
        ok, msg = verify_backup_checksum(backup_zip, "0" * 64)
        assert ok is False
        assert "mismatch" in msg.lower()

    def test_checksum_nonexistent_file(self, tmp_path):
        from hermes_cli.guardian_storage import verify_backup_checksum
        ok, msg = verify_backup_checksum(tmp_path / "nope.zip", "abc")
        assert ok is False
        assert "does not exist" in msg.lower()


# ---------------------------------------------------------------------------
# 6. Database integrity checking
# ---------------------------------------------------------------------------

class TestDatabaseIntegrity:
    """Test database corruption detection."""

    def test_valid_database(self, hermes_home):
        from hermes_cli.guardian_storage import check_database_integrity
        result = check_database_integrity(hermes_home / "state.db")
        assert result["valid"] is True

    def test_missing_database(self, tmp_path):
        from hermes_cli.guardian_storage import check_database_integrity
        result = check_database_integrity(tmp_path / "nonexistent.db")
        assert result["valid"] is False
        assert "does not exist" in result.get("error", "")

    def test_empty_database(self, tmp_path):
        from hermes_cli.guardian_storage import check_database_integrity
        db = tmp_path / "empty.db"
        db.write_bytes(b"")
        result = check_database_integrity(db)
        assert result["valid"] is False
        assert "empty" in result.get("error", "").lower()

    def test_zeroed_database(self, tmp_path):
        from hermes_cli.guardian_storage import check_database_integrity
        db = tmp_path / "zeroed.db"
        db.write_bytes(b"\x00" * 512)
        result = check_database_integrity(db)
        assert result["valid"] is False
        assert "zeroed" in result.get("error", "").lower()

    def test_truncated_database(self, tmp_path):
        from hermes_cli.guardian_storage import check_database_integrity
        db = tmp_path / "truncated.db"
        db.write_bytes(b"SQLite format 3\x00" + b"\x00" * 50)
        result = check_database_integrity(db)
        assert result["valid"] is False

    def test_corrupted_database(self, hermes_home):
        from hermes_cli.guardian_storage import check_database_integrity
        db_path = hermes_home / "state.db"
        # Corrupt the database by appending garbage
        with open(db_path, "ab") as f:
            f.write(b"GARBAGE_DATA" * 100)
        result = check_database_integrity(db_path)
        # SQLite may still pass integrity_check for appended data
        # but at minimum the check should run without crash
        assert "valid" in result

    def test_check_all_databases(self, hermes_home):
        from hermes_cli.guardian_storage import check_all_databases
        results = check_all_databases(hermes_home)
        assert len(results) > 0
        # All test databases should be valid
        for r in results:
            if r["path"].endswith("state.db") or r["path"].endswith("memory_store.db"):
                assert r["valid"] is True


# ---------------------------------------------------------------------------
# 7. Storage location registry
# ---------------------------------------------------------------------------

class TestStorageLocations:
    """Test storage location registry."""

    def test_locations_populated(self, hermes_home):
        from hermes_cli.guardian_storage import _get_storage_locations
        locations = _get_storage_locations(hermes_home)
        assert len(locations) > 0

    def test_config_exists(self, hermes_home):
        from hermes_cli.guardian_storage import _get_storage_locations
        locations = _get_storage_locations(hermes_home)
        config = [l for l in locations if l.name == "config"]
        assert len(config) == 1
        assert config[0].exists is True
        assert config[0].category == "config"

    def test_missing_required_location(self, tmp_path):
        from hermes_cli.guardian_storage import _get_storage_locations
        # Empty directory — required files are missing
        locations = _get_storage_locations(tmp_path)
        config = [l for l in locations if l.name == "config"]
        assert len(config) == 1
        assert config[0].exists is False
        assert config[0].failure.value == "missing_path"

    def test_directory_size_calculated(self, hermes_home):
        from hermes_cli.guardian_storage import _get_storage_locations
        locations = _get_storage_locations(hermes_home)
        skills = [l for l in locations if l.name == "skills"]
        assert len(skills) == 1
        assert skills[0].size_bytes > 0


# ---------------------------------------------------------------------------
# 7b. Configurable storage locations + thresholds
# ---------------------------------------------------------------------------

class TestConfigurableLocations:
    """Test that config.yaml can add monitored paths and tune thresholds."""

    def test_config_adds_extra_location(self, hermes_home):
        import hermes_cli.guardian_storage as gs

        # Simulate a user-configured extra path (e.g. media on another drive)
        media_dir = hermes_home / "media" / "generated"
        media_dir.mkdir(parents=True)
        (media_dir / "image.png").write_bytes(b"\x89PNG fake image")

        config_override = {
            "monitored_paths": [
                {"name": "media", "path": "media/generated", "required": False, "category": "media"},
                {"name": "config", "path": "config.yaml", "required": True},  # dup → skipped
            ]
        }
        with patch.object(gs, "_read_guardian_storage_config", return_value=config_override):
            locations = gs._get_storage_locations(hermes_home)

        media = [l for l in locations if l.name == "media"]
        assert len(media) == 1
        assert media[0].exists is True
        assert media[0].category == "media"
        assert media[0].size_bytes == len(b"\x89PNG fake image")
        # Baseline config location still exists exactly once (dup skipped)
        assert len([l for l in locations if l.name == "config"]) == 1

    def test_config_absolute_path(self, hermes_home, tmp_path):
        import hermes_cli.guardian_storage as gs

        # Absolute external directory (e.g. D:\data on Windows)
        external = tmp_path / "external-store"
        external.mkdir()
        (external / "data.bin").write_bytes(b"x" * 1024)

        config_override = {
            "monitored_paths": [
                {"name": "external_store", "path": str(external), "required": False},
            ]
        }
        with patch.object(gs, "_read_guardian_storage_config", return_value=config_override):
            locations = gs._get_storage_locations(hermes_home)

        locs = [l for l in locations if l.name == "external_store"]
        assert len(locs) == 1
        assert locs[0].exists is True
        assert Path(locs[0].path) == external.resolve()

    def test_thresholds_override(self):
        import hermes_cli.guardian_storage as gs
        from hermes_cli.guardian_storage import StorageLevel, _GB

        # Tighten thresholds: everything under 8GB is now emergency.
        config_override = {
            "normal_gb": 100,
            "warning_gb": 50,
            "high_alert_gb": 20,
            "critical_gb": 10,
        }
        with patch.object(gs, "_read_guardian_storage_config", return_value=config_override):
            assert gs.classify_capacity(int(60 * _GB)) == StorageLevel.WARNING
            assert gs.classify_capacity(int(25 * _GB)) == StorageLevel.HIGH_ALERT
            assert gs.classify_capacity(int(12 * _GB)) == StorageLevel.CRITICAL
            assert gs.classify_capacity(int(5 * _GB)) == StorageLevel.EMERGENCY

    def test_thresholds_inverted_config_is_sane(self):
        """Broken/inverted config must not classify 0 bytes as normal."""
        import hermes_cli.guardian_storage as gs
        from hermes_cli.guardian_storage import StorageLevel, _GB

        config_override = {
            "normal_gb": 5,     # inverted (normal < critical)
            "warning_gb": 10,
            "high_alert_gb": 20,
            "critical_gb": 30,
        }
        with patch.object(gs, "_read_guardian_storage_config", return_value=config_override):
            assert gs.classify_capacity(0) == StorageLevel.EMERGENCY
            assert gs.classify_capacity(int(1 * _GB)) == StorageLevel.EMERGENCY

    def test_thresholds_bad_types_fallback(self):
        """Non-numeric config values fall back to the hardcoded defaults."""
        import hermes_cli.guardian_storage as gs
        from hermes_cli.guardian_storage import StorageLevel, _GB

        config_override = {
            "normal_gb": "bogus",
            "warning_gb": None,
            "high_alert_gb": {},
            "critical_gb": "nope",
        }
        # NOTE: real load_config only deep-merges dicts, so this shape is
        # defensive; the point is classify never crashes on garbage.
        with patch.object(gs, "_read_guardian_storage_config", return_value=config_override):
            assert gs.classify_capacity(int(50 * _GB)) == StorageLevel.NORMAL
            assert gs.classify_capacity(int(3 * _GB)) == StorageLevel.EMERGENCY


# ---------------------------------------------------------------------------
# 8. Storage summary
# ---------------------------------------------------------------------------

class TestStorageSummary:
    """Test the complete storage summary function."""

    def test_summary_structure(self, hermes_home):
        from hermes_cli.guardian_storage import get_storage_summary
        summary = get_storage_summary(hermes_home)
        assert "capacity" in summary
        assert "locations" in summary
        assert "failures" in summary
        assert "databases" in summary
        assert "checked_at" in summary

    def test_summary_capacity_fields(self, hermes_home):
        from hermes_cli.guardian_storage import get_storage_summary
        summary = get_storage_summary(hermes_home)
        cap = summary["capacity"]
        assert "level" in cap
        assert "free_gb" in cap
        assert "total_gb" in cap
        assert "used_percent" in cap

    def test_summary_with_mocked_disk(self, hermes_home):
        from hermes_cli.guardian_storage import get_storage_summary
        fake_usage = type("Usage", (), {"total": 100 * 1024**3, "free": 25 * 1024**3, "used": 75 * 1024**3})()
        with patch("hermes_cli.guardian_storage.shutil.disk_usage", return_value=fake_usage):
            summary = get_storage_summary(hermes_home)
        assert summary["capacity"]["level"] == "warning"
        assert summary["capacity"]["free_gb"] == 25.0


# ---------------------------------------------------------------------------
# 9. should_block_nonessential / is_emergency
# ---------------------------------------------------------------------------

class TestEmergencyBlocking:
    """Test emergency capacity blocking functions."""

    def test_emergency_detection(self, hermes_home):
        from hermes_cli.guardian_storage import should_block_nonessential, _GB
        fake_usage = type("Usage", (), {"free": int(3 * _GB)})()
        with patch("hermes_cli.guardian_storage.shutil.disk_usage", return_value=fake_usage):
            assert should_block_nonessential(hermes_home) is True

    def test_normal_no_blocking(self, hermes_home):
        from hermes_cli.guardian_storage import should_block_nonessential, _GB
        fake_usage = type("Usage", (), {"free": int(50 * _GB)})()
        with patch("hermes_cli.guardian_storage.shutil.disk_usage", return_value=fake_usage):
            assert should_block_nonessential(hermes_home) is False

    def test_emergency_disk_check_failure(self, hermes_home):
        from hermes_cli.guardian_storage import should_block_nonessential
        with patch("hermes_cli.guardian_storage.shutil.disk_usage", side_effect=OSError("no disk")):
            # On failure, default to safe (don't block)
            assert should_block_nonessential(hermes_home) is False
