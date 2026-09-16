"""Tests for guardian_recovery.py — Guardian 2 Recovery Test Runner.

Tests the actual backup→verify→restore→verify→start→test flow.
Uses isolated temporary directories — never touches real HERMES_HOME.
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
def source_hermes_home(tmp_path):
    """Create a realistic source HERMES_HOME for recovery testing."""
    from hermes_cli.guardian_recovery import _make_test_hermes_home
    home = tmp_path / "source_hermes"
    _make_test_hermes_home(home)
    return home


@pytest.fixture
def minimal_hermes_home(tmp_path):
    """Create a minimal HERMES_HOME with just config and one DB."""
    home = tmp_path / "minimal_hermes"
    home.mkdir()

    (home / "config.yaml").write_text("model:\n  provider: test\n", encoding="utf-8")
    (home / ".env").write_text("TEST_KEY=test\n", encoding="utf-8")

    with sqlite3.connect(str(home / "state.db")) as conn:
        conn.execute("CREATE TABLE t (v TEXT)")
        conn.execute("INSERT INTO t VALUES ('minimal')")
        conn.commit()

    return home


# ---------------------------------------------------------------------------
# Backup creation helpers
# ---------------------------------------------------------------------------

class TestBackupCreation:
    """Test backup creation helpers in isolation."""

    def test_full_zip_creates_archive(self, source_hermes_home, tmp_path):
        from hermes_cli.guardian_recovery import _backup_full_zip
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        result = _backup_full_zip(source_hermes_home, backup_dir)
        assert result is not None
        assert result.exists()
        assert result.suffix == ".zip"
        assert result.stat().st_size > 0

    def test_full_zip_contains_markers(self, source_hermes_home, tmp_path):
        from hermes_cli.guardian_recovery import _backup_full_zip
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        result = _backup_full_zip(source_hermes_home, backup_dir)
        assert result is not None

        with zipfile.ZipFile(result, "r") as zf:
            names = zf.namelist()
            basenames = [Path(n).name for n in names]
            assert "config.yaml" in basenames
            assert ".env" in basenames
            assert "state.db" in basenames

    def test_full_zip_excludes_pycache(self, source_hermes_home, tmp_path):
        from hermes_cli.guardian_recovery import _backup_full_zip
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        # Create __pycache__ in source
        pycache = source_hermes_home / "skills" / "__pycache__"
        pycache.mkdir(parents=True)
        (pycache / "module.pyc").write_bytes(b"bytecode")

        result = _backup_full_zip(source_hermes_home, backup_dir)
        assert result is not None

        with zipfile.ZipFile(result, "r") as zf:
            names = zf.namelist()
            assert not any("__pycache__" in n for n in names)

    def test_quick_snapshot_creates_directory(self, source_hermes_home, tmp_path):
        from hermes_cli.guardian_recovery import _backup_quick_snapshot
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        result = _backup_quick_snapshot(source_hermes_home, backup_dir)
        assert result is not None
        assert result.is_dir()
        assert (result / "config.yaml").exists()

    def test_quick_snapshot_has_manifest(self, source_hermes_home, tmp_path):
        from hermes_cli.guardian_recovery import _backup_quick_snapshot
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        result = _backup_quick_snapshot(source_hermes_home, backup_dir)
        assert result is not None
        manifest_path = result / "manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert isinstance(manifest, dict)

    def test_quick_snapshot_empty_source(self, tmp_path):
        from hermes_cli.guardian_recovery import _backup_quick_snapshot
        empty_source = tmp_path / "empty_source"
        empty_source.mkdir()
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        result = _backup_quick_snapshot(empty_source, backup_dir)
        assert result is None


# ---------------------------------------------------------------------------
# Restore helpers
# ---------------------------------------------------------------------------

class TestRestoreHelpers:
    """Test restore helper functions."""

    def test_restore_from_zip(self, source_hermes_home, tmp_path):
        from hermes_cli.guardian_recovery import _backup_full_zip, _restore_from_zip
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        restore_target = tmp_path / "restored"
        restore_target.mkdir()

        backup = _backup_full_zip(source_hermes_home, backup_dir)
        assert backup is not None

        _restore_from_zip(backup, restore_target)

        assert (restore_target / "config.yaml").exists()
        assert (restore_target / ".env").exists()
        assert (restore_target / "state.db").exists()

    def test_restore_from_zip_content_matches(self, source_hermes_home, tmp_path):
        from hermes_cli.guardian_recovery import _backup_full_zip, _restore_from_zip
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        restore_target = tmp_path / "restored"
        restore_target.mkdir()

        backup = _backup_full_zip(source_hermes_home, backup_dir)
        _restore_from_zip(backup, restore_target)

        # Config content should match
        original = (source_hermes_home / "config.yaml").read_text(encoding="utf-8")
        restored = (restore_target / "config.yaml").read_text(encoding="utf-8")
        assert original == restored

    def test_restore_from_snapshot(self, source_hermes_home, tmp_path):
        from hermes_cli.guardian_recovery import _backup_quick_snapshot, _restore_from_snapshot
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        restore_target = tmp_path / "restored"
        restore_target.mkdir()

        snap = _backup_quick_snapshot(source_hermes_home, backup_dir)
        assert snap is not None

        _restore_from_snapshot(snap, restore_target)
        assert (restore_target / "config.yaml").exists()

    def test_path_traversal_blocked(self, tmp_path):
        """Verify that path traversal in zip entries is blocked."""
        from hermes_cli.guardian_recovery import _restore_from_zip

        evil_zip = tmp_path / "evil.zip"
        with zipfile.ZipFile(evil_zip, "w") as zf:
            zf.writestr("../../../etc/passwd", "evil content")
            zf.writestr("config.yaml", "good content")

        restore_target = tmp_path / "restored"
        restore_target.mkdir()

        _restore_from_zip(evil_zip, restore_target)

        # The traversal entry should NOT create files outside restore_target
        outside_file = tmp_path / "etc" / "passwd"
        assert not outside_file.exists()


# ---------------------------------------------------------------------------
# SHA-256 helpers
# ---------------------------------------------------------------------------

class TestHashing:
    """Test file and directory hashing."""

    def test_sha256_file(self, tmp_path):
        from hermes_cli.guardian_recovery import _sha256_file
        test_file = tmp_path / "test.bin"
        test_file.write_bytes(b"hello world")
        h = _sha256_file(test_file)
        assert len(h) == 64
        assert isinstance(h, str)

    def test_sha256_file_deterministic(self, tmp_path):
        from hermes_cli.guardian_recovery import _sha256_file
        test_file = tmp_path / "test.bin"
        test_file.write_bytes(b"deterministic content")
        h1 = _sha256_file(test_file)
        h2 = _sha256_file(test_file)
        assert h1 == h2

    def test_sha256_directory(self, source_hermes_home):
        from hermes_cli.guardian_recovery import _sha256_directory
        h = _sha256_directory(source_hermes_home)
        assert len(h) == 64

    def test_sha256_directory_empty(self, tmp_path):
        from hermes_cli.guardian_recovery import _sha256_directory
        empty = tmp_path / "empty"
        empty.mkdir()
        h = _sha256_directory(empty)
        # Empty dir should have a consistent hash
        assert len(h) == 64


# ---------------------------------------------------------------------------
# Full recovery test — full_zip
# ---------------------------------------------------------------------------

class TestRecoveryFullZip:
    """Test the complete recovery flow with full zip backup."""

    def test_full_recovery_passes(self, source_hermes_home):
        from hermes_cli.guardian_recovery import run_recovery_test, RecoveryStatus

        result = run_recovery_test(
            test_type="full_zip",
            source_home=source_hermes_home,
        )

        assert result.overall_status == RecoveryStatus.PASSED
        assert len(result.steps) == 7
        assert all(s.status == "passed" for s in result.steps)
        assert result.backup_path != ""
        assert result.restore_path != ""
        assert result.files_after > 0

    def test_recovery_steps_have_timing(self, source_hermes_home):
        from hermes_cli.guardian_recovery import run_recovery_test

        result = run_recovery_test(
            test_type="full_zip",
            source_home=source_hermes_home,
        )

        for step in result.steps:
            assert step.duration_ms >= 0

    def test_recovery_has_timestamps(self, source_hermes_home):
        from hermes_cli.guardian_recovery import run_recovery_test

        result = run_recovery_test(
            test_type="full_zip",
            source_home=source_hermes_home,
        )

        assert result.started_at != ""
        assert result.finished_at != ""


# ---------------------------------------------------------------------------
# Full recovery test — quick_snapshot
# ---------------------------------------------------------------------------

class TestRecoveryQuickSnapshot:
    """Test the complete recovery flow with quick snapshot backup."""

    def test_quick_snapshot_recovery_passes(self, source_hermes_home):
        from hermes_cli.guardian_recovery import run_recovery_test, RecoveryStatus

        result = run_recovery_test(
            test_type="quick_snapshot",
            source_home=source_hermes_home,
        )

        assert result.overall_status == RecoveryStatus.PASSED
        assert len(result.steps) == 7
        assert all(s.status == "passed" for s in result.steps)


# ---------------------------------------------------------------------------
# Recovery test with minimal HERMES_HOME
# ---------------------------------------------------------------------------

class TestRecoveryMinimal:
    """Test recovery with minimal source."""

    def test_minimal_recovery_passes(self, minimal_hermes_home):
        from hermes_cli.guardian_recovery import run_recovery_test, RecoveryStatus

        result = run_recovery_test(
            test_type="full_zip",
            source_home=minimal_hermes_home,
        )

        assert result.overall_status == RecoveryStatus.PASSED


# ---------------------------------------------------------------------------
# Recovery test edge cases
# ---------------------------------------------------------------------------

class TestRecoveryEdgeCases:
    """Test recovery edge cases."""

    def test_nonexistent_source_fails(self, tmp_path):
        from hermes_cli.guardian_recovery import run_recovery_test, RecoveryStatus

        nonexistent = tmp_path / "nonexistent"
        result = run_recovery_test(
            test_type="full_zip",
            source_home=nonexistent,
        )

        assert result.overall_status == RecoveryStatus.FAILED
        assert len(result.errors) > 0

    def test_recovery_result_structure(self, source_hermes_home):
        from hermes_cli.guardian_recovery import run_recovery_test

        result = run_recovery_test(
            test_type="full_zip",
            source_home=source_hermes_home,
        )

        step_names = [s.name for s in result.steps]
        assert "BACKUP" in step_names
        assert "VERIFY_BACKUP" in step_names
        assert "ISOLATE" in step_names
        assert "RESTORE" in step_names
        assert "VERIFY_RESTORE" in step_names
        assert "START" in step_names
        assert "TEST" in step_names

    def test_checksum_recorded(self, source_hermes_home):
        from hermes_cli.guardian_recovery import run_recovery_test

        result = run_recovery_test(
            test_type="full_zip",
            source_home=source_hermes_home,
        )

        assert result.checksum_before != ""
        assert len(result.checksum_before) == 64


# ---------------------------------------------------------------------------
# Integration: backup → verify checksum roundtrip
# ---------------------------------------------------------------------------

class TestBackupVerifyRoundtrip:
    """Test that backup checksums round-trip correctly."""

    def test_checksum_roundtrip(self, source_hermes_home, tmp_path):
        from hermes_cli.guardian_recovery import _backup_full_zip, _sha256_file

        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        backup = _backup_full_zip(source_hermes_home, backup_dir)
        assert backup is not None

        # Compute checksum
        checksum = _sha256_file(backup)

        # Verify it matches
        from hermes_cli.guardian_storage import verify_backup_checksum
        ok, msg = verify_backup_checksum(backup, checksum)
        assert ok is True

    def test_backup_verification_passes(self, source_hermes_home, tmp_path):
        from hermes_cli.guardian_recovery import _backup_full_zip
        from hermes_cli.guardian_storage import verify_backup_archive

        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        backup = _backup_full_zip(source_hermes_home, backup_dir)
        assert backup is not None

        result = verify_backup_archive(backup)
        assert result.valid is True
        assert result.has_config is True
        assert result.has_state_db is True
