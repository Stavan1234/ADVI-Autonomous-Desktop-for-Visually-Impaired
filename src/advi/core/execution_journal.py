from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

from .action_plan import Action

logger = logging.getLogger(__name__)


class ExecutionJournal:
    """Durable per-step execution journal used to recover interrupted work safely."""

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
                CREATE TABLE IF NOT EXISTS advi_execution_journal (
                    task_id TEXT NOT NULL,
                    plan_fingerprint TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    action_fingerprint TEXT NOT NULL,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at REAL NOT NULL,
                    finished_at REAL,
                    result_payload TEXT,
                    PRIMARY KEY(task_id, plan_fingerprint, step_index)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_advi_execution_journal_task "
                "ON advi_execution_journal(task_id, started_at DESC)"
            )

    @staticmethod
    def fingerprint_action(action: Action) -> str:
        payload = action.model_dump(mode="json")
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def fingerprint_plan(goal: str, actions: list[Action]) -> str:
        payload = {
            "goal": goal,
            "actions": [a.model_dump(mode="json") for a in actions],
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    def begin(self, task_id: str, plan_fingerprint: str, step_index: int, action: Action) -> None:
        now = time.time()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO advi_execution_journal(
                    task_id, plan_fingerprint, step_index, action_fingerprint,
                    action, status, started_at, finished_at, result_payload
                ) VALUES (?, ?, ?, ?, ?, 'started', ?, NULL, NULL)
                """,
                (
                    task_id,
                    plan_fingerprint,
                    step_index,
                    self.fingerprint_action(action),
                    action.action,
                    now,
                ),
            )

    def finish(self, task_id: str, plan_fingerprint: str, step_index: int, result: Any) -> None:
        payload = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE advi_execution_journal
                SET status = 'finished', finished_at = ?, result_payload = ?
                WHERE task_id = ? AND plan_fingerprint = ? AND step_index = ?
                """,
                (
                    time.time(),
                    json.dumps(payload, ensure_ascii=False, default=str),
                    task_id,
                    plan_fingerprint,
                    step_index,
                ),
            )

    def interrupted_step(self, task_id: str, plan_fingerprint: str | None = None) -> dict[str, Any] | None:
        query = (
            "SELECT * FROM advi_execution_journal "
            "WHERE task_id = ? AND status = 'started'"
        )
        params: list[Any] = [task_id]
        if plan_fingerprint is not None:
            query += " AND plan_fingerprint = ?"
            params.append(plan_fingerprint)
        query += " ORDER BY started_at DESC LIMIT 1"

        with self._connect() as connection:
            row = connection.execute(query, params).fetchone()
        return dict(row) if row else None

    def clear_interrupted(self, task_id: str, plan_fingerprint: str, step_index: int) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM advi_execution_journal "
                "WHERE task_id = ? AND plan_fingerprint = ? AND step_index = ? AND status = 'started'",
                (task_id, plan_fingerprint, step_index),
            )
