from pathlib import Path

from advi.brain.task_state import ActiveTask, TaskStatus
from advi.core.action_plan import Action, ActionPlan, ExecutionResult
from advi.core.execution_journal import ExecutionJournal
from advi.core.task_persistence import TaskPersistence


def test_journal_detects_interrupted_step(tmp_path: Path):
    journal = ExecutionJournal(tmp_path / "journal.db")
    action = Action(action="save_file", parameters={"path": "x.txt", "text": "hello"})
    plan = ActionPlan(goal="save", actions=[action])
    fp = ExecutionJournal.fingerprint_plan(plan.goal, plan.actions)
    journal.begin("t1", fp, 0, action)

    interrupted = journal.interrupted_step("t1", fp)
    assert interrupted is not None
    assert interrupted["action"] == "save_file"


def test_finished_step_is_not_considered_interrupted(tmp_path: Path):
    journal = ExecutionJournal(tmp_path / "journal.db")
    action = Action(action="search", parameters={"query": "hello"})
    plan = ActionPlan(goal="search", actions=[action])
    fp = ExecutionJournal.fingerprint_plan(plan.goal, plan.actions)
    journal.begin("t1", fp, 0, action)
    journal.finish("t1", fp, 0, ExecutionResult(action="search", success=True))

    assert journal.interrupted_step("t1", fp) is None


def test_persisted_approval_cannot_mask_interrupted_execution(tmp_path: Path):
    journal = ExecutionJournal(tmp_path / "journal.db")
    action = Action(action="save_file", parameters={"path": "x.txt", "text": "hello"})
    plan = ActionPlan(goal="save", actions=[action])
    fp = ExecutionJournal.fingerprint_plan(plan.goal, plan.actions)
    journal.begin("t1", fp, 0, action)

    store = TaskPersistence(tmp_path / "tasks.db")
    task = ActiveTask(goal="save", task_id="t1", status=TaskStatus.IN_PROGRESS, plan=plan)
    store.save(task)
    loaded = store.get("t1")
    assert loaded is not None
    assert loaded.status == TaskStatus.IN_PROGRESS
    assert journal.interrupted_step("t1", fp) is not None


def test_agent_marks_interrupted_task_for_explicit_review(tmp_path):
    from advi.brain.agent import ADVIAgent
    from advi.core.execution_journal import ExecutionJournal

    action = Action(action="save_file", parameters={"path": "x.txt", "text": "hello"})
    plan = ActionPlan(goal="save", actions=[action])
    journal = ExecutionJournal(tmp_path / "journal.db")
    fingerprint = ExecutionJournal.fingerprint_plan(plan.goal, plan.actions)
    journal.begin("t2", fingerprint, 0, action)

    task = ActiveTask(goal="save", task_id="t2", plan=plan)
    agent = ADVIAgent(provider=type("P", (), {"generate": lambda self, prompt: None})(), execution_journal=journal, resume_task=False)
    agent._mark_interrupted_task(task)

    assert task.status == TaskStatus.AWAITING_INPUT
    assert task.waiting_for == "interrupted_execution_review"
    assert task.context["_interrupted_step"]["action"] == "save_file"
