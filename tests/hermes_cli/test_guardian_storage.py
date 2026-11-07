"""Invariants for Guardian storage accounting.

The home contains vendored ``node_modules`` and virtualenvs, so the recursive
size walk and the ``PRAGMA integrity_check`` sweep are opt-in extras for
interactive surfaces. These tests pin that contract without timing assertions:
the fast path must report zero work done rather than a stale number, and the
full path must still account for every file and database.
"""

from __future__ import annotations

import sqlite3

from hermes_cli import guardian_storage


def test_dir_size_counts_nested_files(tmp_path):
    tree = tmp_path / "tree"
    (tree / "a" / "b").mkdir(parents=True)
    (tree / "a" / "one.bin").write_bytes(b"x" * 10)
    (tree / "a" / "b" / "two.bin").write_bytes(b"y" * 25)

    assert guardian_storage._dir_size(tree) == 35


def test_capacity_skips_the_hermes_size_walk_on_request(tmp_path):
    home = tmp_path / "hermes_test"
    (home / "state.db").write_bytes(b"")

    quick = guardian_storage.check_disk_capacity(home, include_hermes_size=False)
    full = guardian_storage.check_disk_capacity(home)

    assert quick.hermes_size_bytes == 0
    assert full.hermes_size_bytes > 0
    # The cheap path still catalogs every location; only the walk is skipped.
    assert len(quick.locations) == len(full.locations)
    assert quick.total_bytes > 0


def test_summary_skips_the_database_sweep_on_request(tmp_path):
    home = tmp_path / "hermes_test"
    home.mkdir(exist_ok=True)
    conn = sqlite3.connect(home / "state.db")
    try:
        conn.execute("create table t (x integer)")
        conn.commit()
    finally:
        conn.close()

    quick = guardian_storage.get_storage_summary(
        home, include_databases=False, include_hermes_size=False
    )
    full = guardian_storage.get_storage_summary(home, include_hermes_size=False)

    assert quick["databases"] == []
    assert any(row["path"].endswith("state.db") for row in full["databases"])
