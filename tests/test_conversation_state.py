from advi.brain.context import AgentContext
from advi.brain.conversation_state import ConversationState
from advi.brain.task_state import ActiveTask, TaskStatus
from advi.core.action_plan import ExecutionResult


def test_completed_task_remains_current_for_conversational_continuity():
    state = ConversationState()
    task = ActiveTask(goal="draft an email to Joel")
    task.mark_completed()
    state.set_task(task)

    assert state.current_task is task
    assert state.current_task.status is TaskStatus.COMPLETED


def test_new_task_archives_previous_work():
    state = ConversationState()
    first = ActiveTask(goal="draft an email to Joel")
    second = ActiveTask(goal="open Chrome")

    state.set_task(first)
    state.set_task(second)

    assert state.current_task is second
    assert [task.goal for task in state.recent_tasks] == [first.goal]


def test_recent_results_are_bounded_and_json_friendly():
    state = ConversationState(max_recent_results=2)
    results = [
        ExecutionResult(action="one", success=True),
        ExecutionResult(action="two", success=True),
        ExecutionResult(action="three", success=False, error="failed"),
    ]

    state.add_results(results)

    assert [item["action"] for item in state.recent_results] == ["two", "three"]
    assert state.recent_results[-1]["error"] == "failed"


def test_context_exposes_recent_work_without_replacing_current_task():
    state = ConversationState()
    old = ActiveTask(goal="draft an email")
    current = ActiveTask(goal="open Chrome")
    state.set_task(old)
    state.set_task(current)

    context = AgentContext(
        current_message="continue",
        active_task=current.to_dict(),
        recent_tasks=[task.to_dict() for task in state.recent_tasks],
    )

    formatted = context.format_prompt_context()

    assert "Active Task Context" in formatted
    assert "open Chrome" in formatted
    assert "Recent Work" in formatted
    assert "draft an email" in formatted
