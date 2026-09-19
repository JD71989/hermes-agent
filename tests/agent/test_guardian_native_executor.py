from __future__ import annotations

import json

from agent.guardian import native_executor, workflow_engine as store


def _temp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_WORKFLOW_HOME", tmp_path / "guardian")
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "guardian" / "workflows.db")


def test_crypto_stage_uses_native_tool_dispatch(tmp_path, monkeypatch):
    _temp_store(tmp_path, monkeypatch)
    workflow = store.create_workflow(
        engine="crypto",
        name="Crypto native test",
        mission="collect native market data",
        profile="default",
    )
    calls = []

    def fake_dispatch(name, args):
        calls.append((name, args))
        if name == "crypto_market_intel":
            return json.dumps({"query": args["query"], "coins": [{"id": "bitcoin"}]})
        return json.dumps({"ok": True})

    monkeypatch.setattr("tools.registry.registry.dispatch", fake_dispatch)
    result = native_executor.execute_stage(workflow)
    assert result.status == "completed"
    assert [name for name, _ in calls] == ["crypto_market_intel", "crypto_market_intel"]


def test_missing_native_engine_is_blocked(tmp_path, monkeypatch):
    _temp_store(tmp_path, monkeypatch)
    workflow = store.create_workflow(
        engine="bond",
        name="Bond gate test",
        mission="qualified leads",
        profile="default",
    )
    result = native_executor.execute_stage(workflow)
    assert result.status == "blocked"
    assert result.blocker == "BOND_EXECUTOR_OR_KEY_MISSING"
