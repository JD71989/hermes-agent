from pathlib import Path

from guardian_os.registry import build_plugin_spec


def test_plugin_factory_spec_is_non_deploying():
    spec = build_plugin_spec(
        "test idea",
        departments=["marketing", "engineering"],
        agents=["researcher"],
        capabilities=["web_research"],
        revenue_models=["affiliate"],
    )
    assert spec["external_actions_enabled"] is False
    assert spec["approval_gates"] == ["validate", "build", "test", "deploy"]


def test_idea_lab_page_exists():
    page = Path("web/src/pages/GuardianIdeaLabPage.tsx")
    assert page.exists()
    assert "Run validation gate" in page.read_text(encoding="utf-8")
