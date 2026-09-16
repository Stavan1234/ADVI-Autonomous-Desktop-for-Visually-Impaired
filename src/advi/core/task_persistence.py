from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

from advi.brain.task_state import ActiveTask, TaskStatus
from .action_plan import ActionPlan, ExecutionResult

logger = logging.getLogger(__name__)


class TaskPersistence:
    """Small durable store for resumable ADVI task state.

    This is persistence, not orchestration: it stores snapshots and retrieves
    them. Lifecycle decisions remain owned by ConversationState/ADVIAgent.
    """

    RESUMABLE_STATUSES = {
        TaskStatus.IN_PROGRESS,
        TaskStatus.AWAITING_INPUT,
        TaskStatus.AWAITING_CONFIRMATION,
    }

    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS advi_tasks (
                    task_id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    archived_at REAL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_advi_tasks_status_updated "
                "ON advi_tasks(status, updated_at DESC)"
            )

    @staticmethod
    def _json_default(value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, (set, tuple)):
            return list(value)
        return str(value)

    def save(self, task: ActiveTask) -> None:
        payload = {
            "task_id": task.task_id,
            "goal": task.goal,
            "status": task.status.value,
            "entities": task.entities,
            "context": task.context,
            "revisions": task.revisions,
            "plan": task.plan.model_dump(mode="json") if task.plan else None,
            "results": [result.model_dump(mode="json") for result in task.results],
            "waiting_for": task.waiting_for,
            "confirmation": {
                "details": task.context.get("confirmation_details", ""),
                # Approval must never survive a process restart.
                "invalidated_on_restart": task.confirmation_fingerprint is not None,
            },
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        }
        timestamp = time.time()
        serialized = json.dumps(payload, default=self._json_default, ensure_ascii=False)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO advi_tasks(task_id, goal, status, payload, created_at, updated_at, archived_at)
                VALUES (?, ?, ?, ?, ?, ?, NULL)
                ON CONFLICT(task_id) DO UPDATE SET
                    goal=excluded.goal,
                    status=excluded.status,
                    payload=excluded.payload,
                    updated_at=excluded.updated_at,
                    archived_at=CASE
                        WHEN excluded.status IN ('completed', 'failed', 'cancelled')
                        THEN excluded.updated_at
                        ELSE NULL
                    END
                """,
                (task.task_id, task.goal, task.status.value, serialized, task.created_at, timestamp),
            )

    def get(self, task_id: str) -> ActiveTask | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM advi_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return self._deserialize(dict(row)["payload"]) if row else None

    def latest_resumable(self) -> ActiveTask | None:
        placeholders = ",".join("?" for _ in self.RESUMABLE_STATUSES)
        statuses = [status.value for status in self.RESUMABLE_STATUSES]
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT payload FROM advi_tasks
                WHERE status IN ({placeholders})
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                statuses,
            ).fetchone()
        return self._deserialize(dict(row)["payload"]) if row else None

    def list_resumable(self, limit: int = 10) -> list[ActiveTask]:
        limit = max(1, int(limit))
        placeholders = ",".join("?" for _ in self.RESUMABLE_STATUSES)
        statuses = [status.value for status in self.RESUMABLE_STATUSES]
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT payload FROM advi_tasks
                WHERE status IN ({placeholders})
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                [*statuses, limit],
            ).fetchall()
        return [self._deserialize(dict(row)["payload"]) for row in rows]

    def mark_archived(self, task_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE advi_tasks SET archived_at = ? WHERE task_id = ?",
                (time.time(), task_id),
            )

    def _deserialize(self, raw_payload: str) -> ActiveTask:
        payload = json.loads(raw_payload)
        plan = ActionPlan.model_validate(payload["plan"]) if payload.get("plan") else None
        results = [ExecutionResult.model_validate(item) for item in payload.get("results", [])]
        task = ActiveTask(
            goal=payload["goal"],
            task_id=payload["task_id"],
            status=TaskStatus(payload.get("status", TaskStatus.IN_PROGRESS.value)),
            entities=payload.get("entities") or {},
            context=payload.get("context") or {},
            revisions=payload.get("revisions") or [],
            plan=plan,
            results=results,
            waiting_for=payload.get("waiting_for"),
            created_at=float(payload.get("created_at", time.time())),
            updated_at=float(payload.get("updated_at", time.time())),
            # Never restore an old approval token across process boundaries.
            confirmation_fingerprint=None,
            confirmation_issued_at=None,
            confirmation_expires_at=None,
        )
        if task.status == TaskStatus.AWAITING_CONFIRMATION:
            task.context["confirmation_details"] = (
                (payload.get("confirmation") or {}).get("details")
                or task.context.get("confirmation_details", "")
            )
            task.context["confirmation_invalidated_on_restart"] = True
            # Require a fresh confirmation for the persisted plan.
            task.status = TaskStatus.IN_PROGRESS
            task.waiting_for = None
        return task
