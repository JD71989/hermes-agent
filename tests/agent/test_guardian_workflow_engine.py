from pathlib import Path

from agent.guardian import workflow_engine as engine


def _use_temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "_WORKFLOW_HOME", tmp_path / "guardian")
    monkeypatch.setattr(engine, "DB_PATH", tmp_path / "guardian" / "workflows.db")


def test_all_guardian_engines_have_five_stages():
    assert len(engine.ENGINE_SPECS) == 11
    assert set(engine.ENGINE_SPECS) == {
        "general",
        "news",
        "bond",
        "recovery",
        "crypto",
        "polymarket",
        "pumpfun",
        "pionex",
        "media",
        "voice",
        "web",
    }
    assert all(len(stages) == 5 for stages in engine.ENGINE_SPECS.values())


def test_create_workflow_persists_steps_and_events(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    workflow = engine.create_workflow(
        engine="bond",
        name="Bond acquisition",
        mission="Run the approved lead-generation workflow.",
        profile="default",
    )
    assert workflow["id"].startswith("gw_")
    assert workflow["state"] == "queued"
    assert [s["name"] for s in workflow["steps"]] == [
        "DISCOVER", "QUALIFY", "COMPLIANCE", "DELIVER", "MEASURE"
    ]
    assert workflow["events"][0]["type"] == "created"
