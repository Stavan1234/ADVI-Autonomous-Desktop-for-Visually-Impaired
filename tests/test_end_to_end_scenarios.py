import json
from pathlib import Path

from advi.brain.agent import ADVIAgent
from advi.capabilities.registry import Capability, CapabilityRegistry
from advi.core.action_plan import Action, ExecutionResult
from advi.core.execution_engine import ExecutionEngine
from advi.providers import LLMResponse


class ScenarioProvider:
    name = "scenario"
    model = "scenario-model"

    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    def structured(self, messages, schema):
        self.calls.append(("structured", messages, schema))
        if not self.payloads:
            raise AssertionError("ScenarioProvider ran out of structured responses")
        return LLMResponse(text=json.dumps(self.payloads.pop(0)), provider=self.name, model=self.model)

    def generate(self, prompt):
        self.calls.append(("generate", prompt))
        return LLMResponse(text="", provider=self.name, model=self.model)


class FakeCapabilityHandler:
    def __init__(self):
        self.files = {}
        self.calls = []
        self.context = None

    def execute(self, action):
        self.calls.append(action)
        if action.action == "create_file":
            path = Path(action.parameters["path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(action.parameters["content"], encoding="utf-8")
            return ExecutionResult(
                action=action.action,
                success=True,
                data=str(path),
                human_readable=f"Created {path.name}.",
                verified=True,
                verification_details={"path": str(path)},
            )
        if action.action == "email_send":
            return ExecutionResult(
                action=action.action,
                success=True,
                data={"id": "msg-1"},
                human_readable="Email sent.",
            )
        raise AssertionError(f"Unexpected action: {action.action}")


def make_registry(handler, *actions):
    registry = CapabilityRegistry()
    registry.register(
        Capability(
            name="scenario_capability",
            description="Deterministic scenario capability for end-to-end tests.",
            supported_actions=set(actions),
            handler=handler,
        )
    )
    return registry


def test_end_to_end_create_file_reaches_verified_goal(tmp_path):
    target = tmp_path / "report.txt"
    provider = ScenarioProvider([
        {
            "mode": "action",
            "goal": f"Create {target} containing hello",
            "action": "create_file",
            "confidence": 0.98,
            "missing_information": [],
            "reason": "file creation requested",
        },
        {
            "goal": f"Create {target} containing hello",
            "reason": "create the requested file",
            "missing_information": [],
            "confirmation_required": False,
            "actions": [
                {"action": "create_file", "parameters": {"path": str(target), "content": "hello"}}
            ],
        },
    ])
    handler = FakeCapabilityHandler()
    registry = make_registry(handler, "create_file")
    agent = ADVIAgent(provider, registry=registry, execution_engine=ExecutionEngine(registry=registry))

    response = agent.respond(f"Create {target} containing hello")

    assert target.read_text(encoding="utf-8") == "hello"
    assert handler.calls == [handler.calls[0]]
    assert agent.active_task is not None
    assert agent.active_task.status.value == "completed"
    assert "Done and verified" in response.text
    assert provider.payloads == []


def test_end_to_end_confirmation_is_required_and_then_executes():
    provider = ScenarioProvider([
        {
            "mode": "action",
            "goal": "Send an email to test@example.com with subject Hello and body Hi",
            "action": "email_send",
            "confidence": 0.99,
            "missing_information": [],
            "reason": "user requested an email send",
        },
        {
            "goal": "Send an email to test@example.com with subject Hello and body Hi",
            "reason": "send the email",
            "missing_information": [],
            "confirmation_required": True,
            "confirmation_prompt": "Send the email now?",
            "actions": [
                {
                    "action": "email_send",
                    "parameters": {"to": "test@example.com", "subject": "Hello", "body": "Hi"},
                }
            ],
        },
        {
            "mode": "task_confirm",
            "goal": "yes",
            "confidence": 1.0,
            "missing_information": [],
            "reason": "confirmation phrase",
        },
    ])
    handler = FakeCapabilityHandler()
    registry = make_registry(handler, "email_send")
    agent = ADVIAgent(provider, registry=registry, execution_engine=ExecutionEngine(registry=registry))

    first = agent.respond("Send an email to test@example.com with subject Hello and body Hi")
    assert "Please reply yes or no" in first.text
    assert handler.calls == []
    assert agent.active_task is not None
    assert agent.active_task.status.value == "awaiting_confirmation"

    second = agent.respond("yes")
    assert handler.calls and handler.calls[0].action == "email_send"
    assert agent.active_task is not None
    assert agent.active_task.status.value == "completed"
    assert "Done and verified" in second.text


def test_end_to_end_multiturn_modify_replans_existing_task(tmp_path):
    target = tmp_path / "note.txt"
    provider = ScenarioProvider([
        {
            "mode": "action",
            "goal": f"Create {target}",
            "action": "create_file",
            "confidence": 0.95,
            "missing_information": [],
            "reason": "create file",
        },
        {
            "goal": f"Create {target}",
            "reason": "create it",
            "missing_information": [],
            "confirmation_required": False,
            "actions": [{"action": "create_file", "parameters": {"path": str(target), "content": "first"}}],
        },
        {
            "mode": "task_modify",
            "goal": "change the content",
            "task_update": "change the content to second",
            "confidence": 0.9,
            "missing_information": [],
            "reason": "modification phrase",
        },
        {
            "goal": f"Change {target} content to second",
            "reason": "update file",
            "missing_information": [],
            "confirmation_required": False,
            "actions": [{"action": "create_file", "parameters": {"path": str(target), "content": "second"}}],
        },
    ])
    handler = FakeCapabilityHandler()
    registry = make_registry(handler, "create_file")
    agent = ADVIAgent(provider, registry=registry, execution_engine=ExecutionEngine(registry=registry))

    agent.respond(f"Create {target}")
    response = agent.respond("change the content")

    assert target.read_text(encoding="utf-8") == "second"
    assert len(handler.calls) == 2
    assert agent.active_task is not None
    assert agent.active_task.status.value == "completed"
    assert "Done and verified" in response.text


def test_end_to_end_unavailable_primary_does_not_crash():
    provider = ScenarioProvider([
        {
            "mode": "action",
            "goal": "Use an unavailable capability",
            "action": "search",
            "confidence": 0.95,
            "missing_information": [],
            "reason": "requested browser search",
        },
    ])
    handler = FakeCapabilityHandler()
    registry = make_registry(handler, "read_file")
    agent = ADVIAgent(provider, registry=registry, execution_engine=ExecutionEngine(registry=registry))

    response = agent.respond("Search for something online")

    assert isinstance(response.text, str)
    assert response.text
