from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .task_state import ActiveTask


@dataclass
class ConversationState:
    """Small, explicit state container for one ADVI conversation.

    This is intentionally not a workflow engine. It owns only conversational
    continuity: the current piece of work, recently completed work, and recent
    execution results. Durable memory remains in the memory subsystem.
    """

    current_task: ActiveTask | None = None
    recent_tasks: list[ActiveTask] = field(default_factory=list)
    recent_results: list[dict[str, Any]] = field(default_factory=list)
    turn_count: int = 0
    resumed_task: bool = False
    max_recent_tasks: int = 5
    max_recent_results: int = 10

    def set_task(self, task: ActiveTask) -> ActiveTask:
        """Make a task the current conversational work item."""
        if self.current_task is not None and self.current_task is not task:
            self.archive_task(self.current_task)
        self.current_task = task
        return task

    def archive_task(self, task: ActiveTask | None = None) -> None:
        """Keep a bounded record of previous work for later conversational reference."""
        task = task or self.current_task
        if task is None:
            return
        self.recent_tasks = [t for t in self.recent_tasks if t.task_id != task.task_id]
        self.recent_tasks.append(task)
        if len(self.recent_tasks) > self.max_recent_tasks:
            self.recent_tasks = self.recent_tasks[-self.max_recent_tasks :]

    def clear_current_task(self, archive: bool = True) -> None:
        """Stop treating the current task as current while preserving its history."""
        if archive:
            self.archive_task(self.current_task)
        self.current_task = None

    def add_results(self, results: list[Any]) -> None:
        """Keep a bounded, JSON-friendly cross-turn view of execution results."""
        for result in results:
            if hasattr(result, "model_dump"):
                item = result.model_dump()
            elif hasattr(result, "dict"):
                item = result.dict()
            elif isinstance(result, dict):
                item = dict(result)
            else:
                item = {"value": str(result)}
            self.recent_results.append(item)
        if len(self.recent_results) > self.max_recent_results:
            self.recent_results = self.recent_results[-self.max_recent_results :]

    def record_turn(self) -> None:
        self.turn_count += 1

    def snapshot(self) -> dict[str, Any]:
        """Return structured conversational state for diagnostics/tests."""
        return {
            "turn_count": self.turn_count,
            "resumed_task": self.resumed_task,
            "current_task": self.current_task.to_dict() if self.current_task else None,
            "recent_tasks": [task.to_dict() for task in self.recent_tasks[-self.max_recent_tasks :]],
            "recent_results": list(self.recent_results[-self.max_recent_results :]),
        }
