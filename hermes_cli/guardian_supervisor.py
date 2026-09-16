"""Autonomous Task Supervisor for Guardian 2.

Discovers queued work, dispatches eligible tasks to Hermes, detects
stale RUNNING tasks, safely retries retryable failures, resumes
idempotent interrupted tasks, records results, emits audit events,
updates metrics, and continues to the next eligible task.

Every autonomous loop has: explicit interval, cancellation,
emergency-stop check, authorization check, resource check,
failure isolation, bounded retry, and structured logging.

DO NOT create infinite autonomous loops. The supervisor runs in
bounded cycles controlled by the maintenance scheduler.
"""

from __future__ import annotations

import enum
import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from hermes_constants import get_hermes_home
from agent.guardian.audit import AuditEvent, audit_log

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    DONE = "DONE"
    FAILED = "FAILED"
    RETRY = "RETRY"
    BLOCKED = "BLOCKED"
    DEAD_LETTER = "DEAD-LETTER"


class TaskType(Enum):
    HEALTH_CHECK = "health_check"
    STORAGE_CHECK = "storage_check"
    OPPORTUNITY_REFRESH = "opportunity_refresh"
    CODEBASE_INDEX = "codebase_index"
    RECONCILIATION = "reconciliation"
    BACKUP_VERIFY = "backup_verify"
    AUDIT_MAINTENANCE = "audit_maintenance"
    REPORT_GENERATION = "report_generation"
    DIAGNOSTIC = "diagnostic"


@dataclass
class GuardianTask:
    """A task in the Guardian task lifecycle."""

    task_id: str
    task_type: str
    status: TaskStatus = TaskStatus.QUEUED
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    acknowledged_at: Optional[str] = None
    completed_at: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    result: Optional[str] = None
    failure_reason: Optional[str] = None
    acknowledgement_note: Optional[str] = None
    priority: int = 5  # 1=highest, 10=lowest
    metadata: dict[str, Any] = field(default_factory=dict)
    audit_record: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "acknowledged_at": self.acknowledged_at,
            "completed_at": self.completed_at,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "result": self.result,
            "failure_reason": self.failure_reason,
            "acknowledgement_note": self.acknowledgement_note,
            "priority": self.priority,
            "metadata": self.metadata,
            "audit_record": self.audit_record,
        }


class TaskLifecycleManager:
    """Manages the task lifecycle with persistence and state transitions.

    State machine:
        QUEUED → RUNNING → ACKNOWLEDGED → DONE
        RUNNING → FAILED → RETRY / BLOCKED / DEAD-LETTER
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks: dict[str, GuardianTask] = {}
        self._state_path = Path(get_hermes_home()) / "guardian_tasks.json"
        self._load_state()

    def _load_state(self) -> None:
        """Load persisted task state from disk."""
        try:
            if self._state_path.exists():
                with open(self._state_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for task_data in data.get("tasks", []):
                    task = GuardianTask(
                        task_id=task_data["task_id"],
                        task_type=task_data["task_type"],
                        status=TaskStatus(task_data["status"]),
                        created_at=task_data["created_at"],
                        started_at=task_data.get("started_at"),
                        acknowledged_at=task_data.get("acknowledged_at"),
                        completed_at=task_data.get("completed_at"),
                        retry_count=task_data.get("retry_count", 0),
                        max_retries=task_data.get("max_retries", 3),
                        result=task_data.get("result"),
                        failure_reason=task_data.get("failure_reason"),
                        acknowledgement_note=task_data.get("acknowledgement_note"),
                        priority=task_data.get("priority", 5),
                        metadata=task_data.get("metadata", {}),
                        audit_record=task_data.get("audit_record"),
                    )
                    self._tasks[task.task_id] = task
        except Exception as e:
            logger.warning("Failed to load task state: %s", e)

    def _save_state(self) -> None:
        """Persist task state to disk."""
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            data = {"tasks": [t.to_dict() for t in self._tasks.values()]}
            with open(self._state_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("Failed to save task state: %s", e)

    def create_task(
        self,
        task_type: str,
        *,
        priority: int = 5,
        metadata: Optional[dict[str, Any]] = None,
        max_retries: int = 3,
    ) -> GuardianTask:
        """Create a new task and return it."""
        task_id = f"guardian-{uuid.uuid4().hex[:12]}"
        task = GuardianTask(
            task_id=task_id,
            task_type=task_type,
            priority=priority,
            max_retries=max_retries,
            metadata=metadata or {},
        )
        with self._lock:
            self._tasks[task_id] = task
        self._save_state()
        audit_log(
            AuditEvent.AGENT_STARTED,
            who="guardian-supervisor",
            what=f"Task {task_id} created: {task_type}",
            action="create_task",
            result="allowed",
        )
        return task

    def get_task(self, task_id: str) -> Optional[GuardianTask]:
        with self._lock:
            return self._tasks.get(task_id)

    def start_task(self, task_id: str) -> bool:
        """Transition task from QUEUED to RUNNING."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None or task.status != TaskStatus.QUEUED:
                return False
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now(timezone.utc).isoformat()
        self._save_state()
        audit_log(
            AuditEvent.AGENT_STARTED,
            who="guardian-supervisor",
            what=f"Task {task_id} started",
            action="start_task",
            result="allowed",
        )
        return True

    def acknowledge_task(self, task_id: str, note: Optional[str] = None) -> bool:
        """Transition task from RUNNING to ACKNOWLEDGED."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None or task.status != TaskStatus.RUNNING:
                return False
            task.status = TaskStatus.ACKNOWLEDGED
            task.acknowledged_at = datetime.now(timezone.utc).isoformat()
            task.acknowledgement_note = note
        self._save_state()
        audit_log(
            AuditEvent.TOOL_EXECUTED,
            who="guardian-supervisor",
            what=f"Task {task_id} acknowledged",
            action="acknowledge_task",
            result="allowed",
        )
        return True

    def complete_task(self, task_id: str, result: str) -> bool:
        """Transition task to DONE."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False
            task.status = TaskStatus.DONE
            task.completed_at = datetime.now(timezone.utc).isoformat()
            task.result = result
        self._save_state()
        audit_log(
            AuditEvent.AGENT_STOPPED,
            who="guardian-supervisor",
            what=f"Task {task_id} completed",
            action="complete_task",
            result="allowed",
        )
        return True

    def fail_task(
        self,
        task_id: str,
        reason: str,
        *,
        retryable: bool = True,
    ) -> TaskStatus:
        """Handle task failure with retry logic."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return TaskStatus.FAILED

            task.retry_count += 1
            task.failure_reason = reason

            if retryable and task.retry_count < task.max_retries:
                task.status = TaskStatus.RETRY
                audit_log(
                    AuditEvent.AGENT_INTERRUPTED,
                    who="guardian-supervisor",
                    what=f"Task {task_id} retry {task.retry_count}/{task.max_retries}: {reason}",
                    action="fail_task",
                    result="blocked",
                    failure=reason,
                )
            elif task.retry_count >= task.max_retries:
                task.status = TaskStatus.DEAD_LETTER
                audit_log(
                    AuditEvent.HARDLINE_BLOCKED,
                    who="guardian-supervisor",
                    what=f"Task {task_id} moved to dead-letter after {task.retry_count} retries",
                    action="fail_task",
                    result="blocked",
                    failure=reason,
                )
            else:
                task.status = TaskStatus.FAILED
                audit_log(
                    AuditEvent.AGENT_INTERRUPTED,
                    who="guardian-supervisor",
                    what=f"Task {task_id} failed: {reason}",
                    action="fail_task",
                    result="denied",
                    failure=reason,
                )

        self._save_state()
        return task.status

    def get_queued_tasks(self) -> list[GuardianTask]:
        """Get all QUEUED tasks sorted by priority."""
        with self._lock:
            return sorted(
                [t for t in self._tasks.values() if t.status == TaskStatus.QUEUED],
                key=lambda t: t.priority,
            )

    def get_running_tasks(self) -> list[GuardianTask]:
        """Get all RUNNING tasks."""
        with self._lock:
            return [t for t in self._tasks.values() if t.status == TaskStatus.RUNNING]

    def get_stale_tasks(self, stale_seconds: int = 300) -> list[GuardianTask]:
        """Get RUNNING tasks that have been running longer than stale_seconds."""
        now = time.monotonic()
        stale = []
        with self._lock:
            for task in self._tasks.values():
                if task.status == TaskStatus.RUNNING and task.started_at:
                    try:
                        started = datetime.fromisoformat(task.started_at)
                        age = (datetime.now(timezone.utc) - started).total_seconds()
                        if age > stale_seconds:
                            stale.append(task)
                    except (ValueError, TypeError):
                        pass
        return stale

    def get_all_tasks(self) -> list[GuardianTask]:
        with self._lock:
            return list(self._tasks.values())


# Module-level singleton
_task_lifecycle = TaskLifecycleManager()


def get_task_lifecycle() -> TaskLifecycleManager:
    """Get the module-level task lifecycle manager."""
    return _task_lifecycle
