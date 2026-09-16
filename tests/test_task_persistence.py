from pathlib import Path

from advi.brain.task_state import ActiveTask, TaskStatus
from advi.core.action_plan import Action, ActionPlan, ExecutionResult, VerificationStatus
from advi.core.task_persistence import TaskPersistence


def make_task(status=TaskStatus.IN_PROGRESS):
    task = ActiveTask(
        goal="Create the requested report",
        task_id="persist01",
        status=status,
        entities={"path": "report.txt"},
        context={"note": "keep formatting"},
        revisions=["make it concise"],
        plan=ActionPlan(
            goal="Create the requested report",
            actions=[Action(action="save_file", parameters={"path": "report.txt", "text": "hello"})],
        ),
        results=[ExecutionResult(
            action="save_file",
            success=True,
            human_readable="Saved report.txt",
            verified=True,
            verification_status=VerificationStatus.VERIFIED,
        )],
        waiting_for="confirmation" if status == TaskStatus.AWAITING_CONFIRMATION else None,
    )
    return task


def test_round_trip_preserves_resumable_task(tmp_path: Path):
    store = TaskPersistence(tmp_path / "tasks.db")
    task = make_task()
    store.save(task)

    loaded = store.get(task.task_id)

    assert loaded is not None
    assert loaded.goal == task.goal
    assert loaded.entities == task.entities
    assert loaded.revisions == task.revisions
    assert loaded.plan is not None
    assert loaded.plan.actions[0].parameters["path"] == "report.txt"
    assert loaded.results[0].success is True


def test_confirmation_is_invalidated_after_restart(tmp_path: Path):
    store = TaskPersistence(tmp_path / "tasks.db")
    task = make_task(TaskStatus.AWAITING_CONFIRMATION)
    task.confirmation_fingerprint = "secret-token"
    task.confirmation_issued_at = 1.0
    task.confirmation_expires_at = 2.0
    store.save(task)

    loaded = store.get(task.task_id)

    assert loaded is not None
    assert loaded.confirmation_fingerprint is None
    assert loaded.confirmation_issued_at is None
    assert loaded.confirmation_expires_at is None
    assert loaded.status == TaskStatus.IN_PROGRESS
    assert loaded.context["confirmation_invalidated_on_restart"] is True


def test_latest_resumable_ignores_terminal_tasks(tmp_path: Path):
    store = TaskPersistence(tmp_path / "tasks.db")
    completed = make_task(TaskStatus.COMPLETED)
    running = make_task(TaskStatus.AWAITING_INPUT)
    running.task_id = "persist02"
    store.save(completed)
    store.save(running)

    latest = store.latest_resumable()

    assert latest is not None
    assert latest.task_id == "persist02"
    assert latest.status == TaskStatus.AWAITING_INPUT
