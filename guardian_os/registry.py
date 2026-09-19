"""Guardian OS department/plugin registry and plugin-factory primitives."""
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

@dataclass(frozen=True)
class Department:
    id: str
    name: str
    capabilities: tuple[str, ...]

@dataclass(frozen=True)
class BusinessPlugin:
    id: str
    name: str
    version: str
    status: str
    departments: tuple[str, ...]
    agents: tuple[str, ...]
    capabilities: tuple[str, ...]
    revenue_models: tuple[str, ...]
    risk_controls: dict[str, Any]
    external_actions_enabled: bool = False

class GuardianRegistry:
    """Provider-neutral registry for Guardian departments and business plugins."""
    def __init__(self, departments: list[Department], plugins: list[BusinessPlugin]) -> None:
        self.departments = {d.id: d for d in departments}
        self.plugins = {p.id: p for p in plugins}

    def plugin(self, plugin_id: str) -> BusinessPlugin:
        return self.plugins[plugin_id]

    def resolve_departments(self, plugin_id: str) -> tuple[Department, ...]:
        plugin = self.plugin(plugin_id)
        return tuple(self.departments[d] for d in plugin.departments)

    def missing_capabilities(self, plugin_id: str) -> tuple[str, ...]:
        plugin = self.plugin(plugin_id)
        available = {c for d in self.resolve_departments(plugin_id) for c in d.capabilities}
        return tuple(sorted(set(plugin.capabilities) - available))
    def validate_plugin(self, plugin_id: str) -> tuple[str, ...]:
        plugin = self.plugin(plugin_id)
        errors: list[str] = []
        for department_id in plugin.departments:
            if department_id not in self.departments:
                errors.append(f"unknown department: {department_id}")
        errors.extend(f"missing capability: {c}" for c in self.missing_capabilities(plugin_id))
        if plugin.external_actions_enabled and plugin.risk_controls.get("human_review_required", False):
            errors.append("external actions require an explicit approval transition")
        return tuple(errors)

def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))

def load_registry(root: str | Path) -> GuardianRegistry:
    root = Path(root)
    department_data = _load_json(root / "departments" / "departments.json")
    departments = [
        Department(d["id"], d["name"], tuple(d.get("capabilities", [])))
        for d in department_data["departments"]
    ]
    plugins: list[BusinessPlugin] = []
    for path in sorted((root / "plugins").glob("*.json")):
        data = _load_json(path)
        if data.get("type") == "capability":
            continue
        plugins.append(BusinessPlugin(
            id=data["id"],
            name=data["name"],
            version=data["version"],
            status=data["status"],
            departments=tuple(data.get("departments", [])),
            agents=tuple(data.get("agents", [])),
            capabilities=tuple(data.get("capabilities", [])),
            revenue_models=tuple(data.get("revenue_models", [])),
            risk_controls=dict(data.get("risk_controls", {})),
            external_actions_enabled=bool(data.get("external_actions_enabled", False)),
        ))
    return GuardianRegistry(departments, plugins)

def build_plugin_spec(
    idea: str,
    *,
    departments: list[str],
    agents: list[str],
    capabilities: list[str],
    revenue_models: list[str],
) -> dict[str, Any]:
    """Create a deterministic plugin specification; it performs no deployment."""
    return {
        "idea": idea,
        "departments": departments,
        "agents": agents,
        "capabilities": capabilities,
        "revenue_models": revenue_models,
        "approval_gates": ["validate", "build", "test", "deploy"],
        "external_actions_enabled": False,
    }
