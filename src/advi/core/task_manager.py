from __future__ import annotations

from uuid import uuid4

import json

from .pipeline_trace import (
    set_task_id,
    task_to_dict,
    trace,
    trace_state_transition,
)
from .task import (
    ConfirmationRequest,
    ConfirmationStatus,
    Task,
    TaskStatus,
    TaskStepState,
    TaskStepStatus,
)


class TaskManager:
    """Manage the lifecycle of running tasks."""

    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}
        self._current_task_id: str | None = None
        self._paused_task_ids: list[str] = []

    def _log_transition(
        self,
        operation: str,
        task_id: str,
        before,
        after,
        *,
        current_task_id_before: str | None,
        **extra,
    ) -> None:
        trace_state_transition(
            "task_manager",
            operation,
            before=before,
            after=after,
            task_id=task_id,
            current_task_id_before=current_task_id_before,
            current_task_id_after=self._current_task_id,
            **extra,
        )

    def create(self, actions: list[str]) -> Task:
        current_task_id_before = self._current_task_id
        task = Task(
            task_id=str(uuid4()),
            steps=[TaskStepState(action=action) for action in actions],
        )
        self._tasks[task.task_id] = task
        self._current_task_id = task.task_id
        set_task_id(task.task_id)

        trace(
            "task.created",
            source_component="TaskManager",
            action="create",
            task_id=task.task_id,
            actions=actions,
            task=task_to_dict(task),
        )

        self._log_transition(
            "create",
            task.task_id,
            {"status": "none", "task_id": None},
            task_to_dict(task),
            current_task_id_before=current_task_id_before,
        )

        return task

    def update_context(self, task_id: str, updates: dict[str, str]) -> Task:
        task = self._require(task_id)
        before = dict(task.context)

        changed = False
        for key, value in updates.items():
            key = str(key)
            value = str(value)
            if task.context.get(key) != value:
                task.context[key] = value
                changed = True

        after = dict(task.context)

        trace(
            "task.context_update",
            source_component="TaskManager",
            action="update_context",
            task_id=task_id,
            before=before,
            update=updates,
            after=after,
            changed=changed,
        )

        if changed:
            self.invalidate_confirmation(task_id)

        return task

    def get_context(self, task_id: str) -> dict[str, str]:
        task = self._require(task_id)
        return dict(task.context)

    def current_task(self) -> Task | None:
        if self._current_task_id is None:
            return None
        return self.get(self._current_task_id)

    def pause_current(self) -> Task | None:
        task = self.current_task()
        if task is None:
            return None

        current_task_id_before = self._current_task_id
        before = task_to_dict(task)

        if task.status in {TaskStatus.RUNNING, TaskStatus.AWAITING_CONFIRMATION}:
            task.status = TaskStatus.PAUSED
        if task.task_id not in self._paused_task_ids:
            self._paused_task_ids.append(task.task_id)
        self._current_task_id = None
        set_task_id(None)

        self._log_transition(
            "pause_current",
            task.task_id,
            before,
            task_to_dict(task),
            current_task_id_before=current_task_id_before,
        )

        return task

    def resume_last_paused(self) -> Task | None:
        while self._paused_task_ids:
            task_id = self._paused_task_ids.pop()
            task = self.get(task_id)
            if task is None:
                continue
            if task.status != TaskStatus.PAUSED:
                continue

            current_task_id_before = self._current_task_id
            before = task_to_dict(task)
            task.status = TaskStatus.RUNNING
            self._current_task_id = task.task_id
            set_task_id(task.task_id)

            self._log_transition(
                "resume_last_paused",
                task.task_id,
                before,
                task_to_dict(task),
                current_task_id_before=current_task_id_before,
            )

            return task
        return None

    def paused_tasks(self) -> list[Task]:
        tasks: list[Task] = []
        for task_id in self._paused_task_ids:
            task = self.get(task_id)
            if task is not None:
                tasks.append(task)
        return tasks

    def invalidate_confirmation(self, task_id: str) -> Task:
        current_task_id_before = self._current_task_id
        task = self._require(task_id)
        before = task_to_dict(task)

        if task.confirmation is not None:
            task.confirmation.status = ConfirmationStatus.CANCELLED
            task.confirmation = None

        self._log_transition(
            "invalidate_confirmation",
            task_id,
            before,
            task_to_dict(task),
            current_task_id_before=current_task_id_before,
        )

        return task

    def get(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def start(self, task_id: str) -> Task:
        current_task_id_before = self._current_task_id
        task = self._require(task_id)
        before = task_to_dict(task)

        if task.status != TaskStatus.PENDING:
            trace(
                "task.start.skipped",
                task_id=task_id,
                reason="status_not_pending",
                status=task.status.value,
            )
            return task

        task.status = TaskStatus.RUNNING
        set_task_id(task_id)

        self._log_transition(
            "start",
            task_id,
            before,
            task_to_dict(task),
            current_task_id_before=current_task_id_before,
        )

        return task

    def pause(self, task_id: str) -> Task:
        current_task_id_before = self._current_task_id
        task = self._require(task_id)
        before = task_to_dict(task)

        if task.status == TaskStatus.RUNNING:
            task.status = TaskStatus.PAUSED

        self._log_transition(
            "pause",
            task_id,
            before,
            task_to_dict(task),
            current_task_id_before=current_task_id_before,
        )

        return task

    def resume(self, task_id: str) -> Task:
        current_task_id_before = self._current_task_id
        task = self._require(task_id)
        before = task_to_dict(task)

        if task.status == TaskStatus.PAUSED:
            task.status = TaskStatus.RUNNING
        if task_id in self._paused_task_ids:
            self._paused_task_ids.remove(task_id)
        self._current_task_id = task_id
        set_task_id(task_id)

        self._log_transition(
            "resume",
            task_id,
            before,
            task_to_dict(task),
            current_task_id_before=current_task_id_before,
        )

        return task

    def await_input(
        self,
        task_id: str,
    ) -> Task:
        current_task_id_before = self._current_task_id
        task = self._require(task_id)
        before = task_to_dict(task)

        task.status = TaskStatus.AWAITING_INPUT
        previous_task_id = self._current_task_id
        self._current_task_id = task.task_id

        trace(
            "task_manager.current_task_restored",
            reason="task_awaiting_input",
            task_id=task.task_id,
            previous_task_id=previous_task_id,
            current_task_id=self._current_task_id,
        )

        self._log_transition(
            "await_input",
            task_id,
            before,
            task_to_dict(task),
            current_task_id_before=current_task_id_before,
        )

        return task

    def await_confirmation(self, task_id: str, action: str, summary: str) -> Task:
        current_task_id_before = self._current_task_id
        task = self._require(task_id)
        before = task_to_dict(task)

        task.status = TaskStatus.AWAITING_CONFIRMATION
        previous_task_id = self._current_task_id
        self._current_task_id = task.task_id

        trace(
            "task_manager.current_task_restored",
            reason="task_awaiting_confirmation",
            task_id=task.task_id,
            previous_task_id=previous_task_id,
            current_task_id=self._current_task_id,
        )
        task.confirmation = ConfirmationRequest(action=action, summary=summary)

        self._log_transition(
            "await_confirmation",
            task_id,
            before,
            task_to_dict(task),
            current_task_id_before=current_task_id_before,
            confirmation_action=action,
            confirmation_summary=summary,
        )

        return task

    def approve(self, task_id: str) -> Task:
        current_task_id_before = self._current_task_id
        task = self._require(task_id)
        before = task_to_dict(task)

        if (
            task.status == TaskStatus.AWAITING_CONFIRMATION
            and task.confirmation is not None
        ):
            task.confirmation.status = ConfirmationStatus.APPROVED
            task.confirmation = None
            task.status = TaskStatus.RUNNING

        self._log_transition(
            "approve",
            task_id,
            before,
            task_to_dict(task),
            current_task_id_before=current_task_id_before,
        )

        return task

    def reject(self, task_id: str) -> Task:
        current_task_id_before = self._current_task_id
        task = self._require(task_id)
        before = task_to_dict(task)

        if (
            task.status == TaskStatus.AWAITING_CONFIRMATION
            and task.confirmation is not None
        ):
            task.confirmation.status = ConfirmationStatus.REJECTED
            task.confirmation = None
            task.status = TaskStatus.CANCELLED

        self._log_transition(
            "reject",
            task_id,
            before,
            task_to_dict(task),
            current_task_id_before=current_task_id_before,
        )

        return task

    def append_step(
        self,
        task_id: str,
        action: str,
    ) -> TaskStepState:
        current_task_id_before = self._current_task_id
        task = self._require(task_id)
        before = task_to_dict(task)

        step = TaskStepState(
            action=action,
        )

        task.steps.append(step)

        task.current_step = len(
            task.steps
        ) - 1

        trace_state_transition(
            "task_manager",
            "append_step",
            before=before,
            after=task_to_dict(task),
            task_id=task_id,
            current_task_id_before=current_task_id_before,
            current_task_id_after=self._current_task_id,
            step_index=len(task.steps) - 1,
            step_action=action,
        )

        return step    

    def start_step(self, task_id: str, index: int) -> TaskStepState:
        current_task_id_before = self._current_task_id
        task = self._require(task_id)
        before = task_to_dict(task)

        step = task.steps[index]
        task.current_step = index
        if step.status == TaskStepStatus.PENDING:
            step.status = TaskStepStatus.RUNNING

        trace_state_transition(
            "task_manager",
            "start_step",
            before=before,
            after=task_to_dict(task),
            task_id=task_id,
            current_task_id_before=current_task_id_before,
            current_task_id_after=self._current_task_id,
            step_index=index,
            step_action=step.action,
        )

        return step

    def complete_step(self, task_id: str, index: int, result=None) -> Task:
        current_task_id_before = self._current_task_id
        task = self._require(task_id)
        before = task_to_dict(task)

        step = task.steps[index]
        step.status = TaskStepStatus.COMPLETED
        step.result = result
        step.error = None
        if (
            task.status != TaskStatus.AWAITING_CONFIRMATION
            and all(item.status == TaskStepStatus.COMPLETED for item in task.steps)
        ):
            task.status = TaskStatus.COMPLETED

        if (
            task.status
            == TaskStatus.COMPLETED
            and self._current_task_id
            == task.task_id
        ):
            previous_task_id = (
                self._current_task_id
            )

            self._current_task_id = None

            trace(
                "task_manager.current_task_cleared",
                reason="task_completed",
                task_id=task.task_id,
                previous_task_id=previous_task_id,
                current_task_id=None,
            )    

        trace_state_transition(
            "task_manager",
            "complete_step",
            before=before,
            after=task_to_dict(task),
            task_id=task_id,
            current_task_id_before=current_task_id_before,
            current_task_id_after=self._current_task_id,
            step_index=index,
            step_result=result,
        )

        return task

    def fail_step(self, task_id: str, index: int, error: str) -> Task:
        current_task_id_before = self._current_task_id
        task = self._require(task_id)
        before = task_to_dict(task)

        step = task.steps[index]
        step.status = TaskStepStatus.FAILED
        step.error = error
        task.status = TaskStatus.FAILED
        task.error = error

        if (
            self._current_task_id
            == task.task_id
        ):
            previous_task_id = (
                self._current_task_id
            )

            self._current_task_id = None

            trace(
                "task_manager.current_task_cleared",
                reason="task_failed",
                task_id=task.task_id,
                previous_task_id=previous_task_id,
                current_task_id=None,
            )

        trace_state_transition(
            "task_manager",
            "fail_step",
            before=before,
            after=task_to_dict(task),
            task_id=task_id,
            current_task_id_before=current_task_id_before,
            current_task_id_after=self._current_task_id,
            step_index=index,
            error=error,
        )

        return task

    def cancel(self, task_id: str) -> Task:
        current_task_id_before = self._current_task_id
        task = self._require(task_id)
        before = task_to_dict(task)

        task.status = TaskStatus.CANCELLED

        trace_state_transition(
            "task_manager",
            "cancel",
            before=before,
            after=task_to_dict(task),
            task_id=task_id,
            current_task_id_before=current_task_id_before,
            current_task_id_after=self._current_task_id,
        )

        return task

    def _require(self, task_id: str) -> Task:
        task = self.get(task_id)
        if task is None:
            raise KeyError(f"Unknown task: {task_id}")
        return task
