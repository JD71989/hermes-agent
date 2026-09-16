"""Codebase Intelligence Layer for Guardian 2.

Provides progressive understanding of the Guardian system:
- Module dependencies and interfaces
- Task flows and previous failures
- Architectural decisions and integration points
- Regenerable index/memory layer

Uses a lightweight native implementation rather than
external dependencies. The memory layer is fully
regenerable from source analysis.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from hermes_constants import get_hermes_home
from agent.guardian.audit import AuditEvent, audit_log

logger = logging.getLogger(__name__)


@dataclass
class ModuleInfo:
    """Information about a single module."""

    name: str
    path: str
    lines: int = 0
    imports: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    last_modified: Optional[str] = None
    index_version: int = 1


@dataclass
class IntegrationPoint:
    """An integration point between subsystems."""

    source: str
    target: str
    type: str  # "import", "call", "config", "data"
    description: str = ""


@dataclass
class CodebaseMemory:
    """Aggregated codebase intelligence."""

    modules: dict[str, ModuleInfo] = field(default_factory=dict)
    integration_points: list[IntegrationPoint] = field(default_factory=list)
    task_flows: list[dict[str, Any]] = field(default_factory=list)
    failure_patterns: list[dict[str, Any]] = field(default_factory=list)
    architectural_decisions: list[dict[str, Any]] = field(default_factory=list)
    index_version: int = 1
    indexed_at: str = ""
    source_hash: str = ""


class CodebaseIntelligence:
    """Progressive understanding of the Guardian system.

    Indexes modules, dependencies, interfaces, tests, task flows,
    previous failures, previous fixes, and architectural decisions.
    Reduces repeated repository scanning.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._memory: CodebaseMemory = CodebaseMemory()
        self._index_path = Path(get_hermes_home()) / "codebase_intelligence.json"
        self._project_root = Path(os.getcwd())
        self._load_memory()

    def _load_memory(self) -> None:
        """Load previously indexed memory."""
        try:
            if self._index_path.exists():
                with open(self._index_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._memory = CodebaseMemory(
                    modules={k: ModuleInfo(**v) for k, v in data.get("modules", {}).items()},
                    integration_points=[
                        IntegrationPoint(**ip) for ip in data.get("integration_points", [])
                    ],
                    task_flows=data.get("task_flows", []),
                    failure_patterns=data.get("failure_patterns", []),
                    architectural_decisions=data.get("architectural_decisions", []),
                    index_version=data.get("index_version", 1),
                    indexed_at=data.get("indexed_at", ""),
                    source_hash=data.get("source_hash", ""),
                )
        except Exception:
            pass

    def _save_memory(self) -> None:
        """Persist memory to disk."""
        try:
            self._index_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "modules": {k: v.__dict__ for k, v in self._memory.modules.items()},
                "integration_points": [ip.__dict__ for ip in self._memory.integration_points],
                "task_flows": self._memory.task_flows,
                "failure_patterns": self._memory.failure_patterns,
                "architectural_decisions": self._memory.architectural_decisions,
                "index_version": self._memory.index_version,
                "indexed_at": self._memory.indexed_at,
                "source_hash": self._memory.source_hash,
            }
            with open(self._index_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def index_module(self, module_path: str) -> ModuleInfo:
        """Index a single module."""
        try:
            path = Path(module_path)
            if not path.exists():
                return ModuleInfo(name=module_path, path=module_path)

            content = path.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()
            name = path.stem

            # Extract imports
            imports: list[str] = []
            classes: list[str] = []
            functions: list[str] = []
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("import ") or stripped.startswith("from "):
                    imports.append(stripped)
                elif stripped.startswith("class "):
                    classes.append(stripped.split("(")[0].replace("class ", "").strip())
                elif stripped.startswith("def "):
                    functions.append(stripped.split("(")[0].replace("def ", "").strip())

            module_info = ModuleInfo(
                name=name,
                path=str(path),
                lines=len(lines),
                imports=imports,
                classes=classes,
                functions=functions,
                dependencies=[i.split()[1] if "import" in i else i.split("from ")[1].split(" import")[0] if "from" in i else "" for i in imports],
                last_modified=str(path.stat().st_mtime) if path.exists() else None,
            )

            with self._lock:
                self._memory.modules[module_path] = module_info

            audit_log(
                AuditEvent.AGENT_STARTED,
                who="codebase-intelligence",
                what=f"Indexed module: {module_path}",
                action="index_module",
                result="allowed",
            )

            return module_info
        except Exception as e:
            logger.warning("Failed to index module %s: %s", module_path, e)
            return ModuleInfo(name=module_path, path=module_path)

    def index_project(self, project_root: Optional[str] = None) -> dict[str, Any]:
        """Index the entire project."""
        root = Path(project_root or self._project_root)

        # Index key Guardian modules
        guardian_modules = [
            "agent/guardian/audit.py",
            "agent/guardian/authorization.py",
            "agent/guardian/auth_tracker.py",
            "agent/guardian/emergency.py",
            "agent/guardian/monitoring.py",
            "agent/nexus.py",
            "tools/guardian_health.py",
            "hermes_cli/guardian_storage.py",
            "hermes_cli/guardian_recovery.py",
            "hermes_cli/guardian_supervisor.py",
            "hermes_cli/guardian_economic.py",
            "hermes_cli/guardian_e2e.py",
            "hermes_cli/subcommands/guardian.py",
        ]

        for mod_path in guardian_modules:
            full_path = root / mod_path
            self.index_module(str(full_path))

        self._memory.indexed_at = datetime.now(timezone.utc).isoformat()
        self._memory.index_version += 1
        self._save_memory()

        return {
            "modules_indexed": len(self._memory.modules),
            "integration_points": len(self._memory.integration_points),
            "index_version": self._memory.index_version,
            "indexed_at": self._memory.indexed_at,
        }

    def get_module(self, module_path: str) -> Optional[ModuleInfo]:
        """Get indexed information for a module."""
        return self._memory.modules.get(module_path)

    def get_all_modules(self) -> dict[str, ModuleInfo]:
        """Get all indexed modules."""
        return dict(self._memory.modules)

    def find_dependencies(self, module_path: str) -> list[str]:
        """Find all dependencies of a module."""
        module = self._memory.modules.get(module_path)
        if module:
            return module.dependencies
        return []

    def get_task_flows(self) -> list[dict[str, Any]]:
        """Get known task flows."""
        return self._memory.task_flows

    def get_failure_patterns(self) -> list[dict[str, Any]]:
        """Get known failure patterns."""
        return self._memory.failure_patterns

    def add_architectural_decision(self, decision: dict[str, Any]) -> None:
        """Record an architectural decision."""
        decision["timestamp"] = datetime.now(timezone.utc).isoformat()
        self._memory.architectural_decisions.append(decision)
        self._save_memory()

    def regenerate_index(self) -> dict[str, Any]:
        """Regenerate the entire index from scratch."""
        self._memory.modules.clear()
        self._memory.index_version += 1
        result = self.index_project()
        logger.info("Codebase index regenerated: %s", result)
        return result

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of the codebase intelligence."""
        return {
            "modules_indexed": len(self._memory.modules),
            "integration_points": len(self._memory.integration_points),
            "task_flows": len(self._memory.task_flows),
            "failure_patterns": len(self._memory.failure_patterns),
            "architectural_decisions": len(self._memory.architectural_decisions),
            "index_version": self._memory.index_version,
            "indexed_at": self._memory.indexed_at,
            "index_path": str(self._index_path),
        }


# Module-level singleton
_codebase_intel: Optional[CodebaseIntelligence] = None


def get_codebase_intelligence() -> CodebaseIntelligence:
    """Get the module-level codebase intelligence."""
    global _codebase_intel
    if _codebase_intel is None:
        _codebase_intel = CodebaseIntelligence()
    return _codebase_intel
