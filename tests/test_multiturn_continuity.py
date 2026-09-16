import json
from pathlib import Path

from advi.brain.agent import ADVIAgent
from advi.brain.conversation_state import ConversationState
from advi.brain.task_state import ActiveTask, TaskStatus
from advi.capabilities.registry import Capability, CapabilityRegistry
from advi.core.action_plan import Action, ActionPlan, ExecutionResult
from advi.core.execution_engine import ExecutionEngine
from advi.core.task_persistence import TaskPersistence
from advi.providers import LLMResponse


class SequenceProvider:
    name = "continuity"
    model = "continuity-model"

    def __init__(self, payloads):
        self.payloads = list(payloads)

    def structured(self, messages, schema):
        if not self.payloads:
            raise AssertionError("provider exhausted")
        return LLMResponse(
            text=json.dumps(self.payloads.pop(0)),
            provider=self.name,
            model=self.model,
        )

    def generate(self, prompt):
        return LLMResponse(text="Okay.", provider=self.name, model=self.model)


class Handler:
    def __init__(self):
        self.files: dict[str, str] = {}
        self.calls: list[Action] = []

    def execute(self, action: Action) -> ExecutionResult:
        self.calls.append(action)
        path = Path(action.parameters["path"])
        content = action.parameters.get("content", "")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self.files[str(path)] = content
        return ExecutionResult(
            action=action.action,
            success=True,
            data=str(path),
            human_readable=f"Updated {path.name}.",
            verified=True,
        )


def registry_for(handler: Handler) -> CapabilityRegistry:
    registry = CapabilityRegistry()
    registry.register(
        Capability(
            name="continuity",
            description="Continuity scenario capability.",
            supported_actions={"create_file"},
            handler=handler,
        )
    )
    return registry


def test_completed_task_archives_when_current_task_is_cleared():
    state = ConversationState()
    first = ActiveTask(goal="Create note")
    first.mark_completed()
    state.set_task(first)
    state.clear_current_task()

    assert state.current_task is None
    assert [t.task_id for t in state.recent_tasks] == [first.task_id]


def test_multiturn_create_modify_then_reference_preserves_single_task(tmp_path: Path):
    target = tmp_path / "note.txt"
    provider = SequenceProvider([
        {
            "mode": "action", "goal": f"Create {target}", "action": "create_file",
            "confidence": 0.99, "missing_information": [], "reason": "create",
        },
        {
            "goal": f"Create {target}", "reason": "create",
            "missing_information": [], "confirmation_required": False,
            "actions": [{"action": "create_file", "parameters": {"path": str(target), "content": "first"}}],
        },
        {
            "mode": "task_modify", "goal": "change content", "task_update": "change content to second",
            "confidence": 0.95, "missing_information": [], "reason": "modify",
        },
        {
            "goal": f"Change {target} to second", "reason": "update",
            "missing_information": [], "confirmation_required": False,
            "actions": [{"action": "create_file", "parameters": {"path": str(target), "content": "second"}}],
        },
    ])
    handler = Handler()
    registry = registry_for(handler)
    agent = ADVIAgent(provider, registry=registry, execution_engine=ExecutionEngine(registry=registry))

    agent.respond(f"Create {target}")
    first_task_id = agent.active_task.task_id
    response = agent.respond("change the content")

    assert target.read_text(encoding="utf-8") == "second"
    assert agent.active_task.task_id == first_task_id
    assert agent.active_task.status == TaskStatus.COMPLETED
    assert len(agent.active_task.revisions) == 1
    assert len(handler.calls) == 2
    assert "Done and verified" in response.text


def test_confirmation_after_modification_is_for_new_plan():
    provider = SequenceProvider([
        {
            "mode": "action", "goal": "Send email", "action": "email_send",
            "confidence": 0.99, "missing_information": [], "reason": "send",
        },
        {
            "goal": "Send email", "reason": "send", "missing_information": [],
            "confirmation_required": True, "confirmation_prompt": "Send it?",
            "actions": [{"action": "create_file", "parameters": {"path": "x", "content": "old"}}],
        },
    ])
    handler = Handler()
    registry = registry_for(handler)
    agent = ADVIAgent(provider, registry=registry, execution_engine=ExecutionEngine(registry=registry))
    # This test only asserts that modifying an awaiting-confirmation task drops its approval.
    task = ActiveTask(goal="Send email")
    task.confirmation_fingerprint = "approved"
    task.status = TaskStatus.AWAITING_CONFIRMATION
    agent.active_task = task
    agent.active_task.apply_modification("change recipient")
    assert agent.active_task.confirmation_fingerprint is None


def test_persisted_multiturn_state_restores_and_never_reuses_old_confirmation(tmp_path: Path):
    store = TaskPersistence(tmp_path / "tasks.db")
    task = ActiveTask(goal="Prepare report", task_id="multi01", status=TaskStatus.IN_PROGRESS)
    task.revisions.append("make it concise")
    task.entities["path"] = "report.txt"
    task.plan = ActionPlan(
        goal="Prepare report",
        actions=[Action(action="create_file", parameters={"path": "report.txt", "content": "v1"})],
    )
    task.results.append(ExecutionResult(action="create_file", success=True, human_readable="created", verified=True))
    store.save(task)

    loaded = store.get("multi01")
    assert loaded is not None
    assert loaded.task_id == "multi01"
    assert loaded.revisions == ["make it concise"]
    assert loaded.entities["path"] == "report.txt"
    assert loaded.confirmation_fingerprint is None
