import json
from pathlib import Path

from guardian_os.registry import build_plugin_spec, load_registry

ROOT = Path(__file__).parents[2] / "guardian_os"

def test_departments_and_news_plugin_load():
    registry = load_registry(ROOT)
    assert len(registry.departments) == 7
    assert "marketing" in registry.departments
    assert "security" in registry.departments
    assert "operations" in registry.departments
    news = registry.plugin("news-media")
    assert news.status == "development"
    assert news.external_actions_enabled is False

def test_news_plugin_resolves_declared_capabilities():
    registry = load_registry(ROOT)
    assert registry.missing_capabilities("news-media") == ()
    assert registry.validate_plugin("news-media") == ()

def test_telephone_agent_is_operations_capability():
    data = json.loads((ROOT / "plugins" / "telephone-agent.json").read_text(encoding="utf-8"))
    assert data["department"] == "operations"
    assert "telephony" in data["capabilities"]
    assert data["external_actions_enabled"] is False

def test_plugin_factory_is_non_deploying():
    spec = build_plugin_spec(
        "example business",
        departments=["marketing"],
        agents=["researcher"],
        capabilities=["content"],
        revenue_models=["affiliate"],
    )
    assert spec["approval_gates"] == ["validate", "build", "test", "deploy"]
    assert spec["external_actions_enabled"] is False
