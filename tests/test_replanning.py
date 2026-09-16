from __future__ import annotations

import json

from advi.core.action_plan import Action, ActionPlan, ExecutionResult
from advi.capabilities.registry import Capability, CapabilityRegistry, CapabilityStatus
from advi.core.replanning import ReplanningEngine
from advi.providers import LLMResponse


class FakeProvider:
    name = "fake"
    model = "fake"
    def __init__(self, payloads):
        self.payloads = iter(payloads)
    def structured(self, messages, schema):
        return LLMResponse(text=json.dumps(next(self.payloads)), provider=self.name, model=self.model)
    def generate(self, prompt):
        return LLMResponse(text='{"actions": []}', provider=self.name, model=self.model)


def test_replanner_returns_one_replacement_action():
    provider = FakeProvider([{
        "decision": "replan",
        "reason": "Use the browser search route instead.",
        "action": {"action": "search", "parameters": {"query": "OpenAI"}},
    }])
    engine = ReplanningEngine(provider, max_replans=2)
    decision = engine.decide(
        "search for OpenAI",
        ActionPlan(goal="search for OpenAI", actions=[Action(action="navigate")]),
        [ExecutionResult(action="navigate", success=False, error="page unavailable")],
        Action(action="navigate"),
        ["search"],
        0,
    )
    assert decision.decision == "replan"
    assert decision.action.action == "search"


def test_replanner_is_bounded():
    provider = FakeProvider([{"decision": "replan", "reason": "x", "action": {"action": "search", "parameters": {}}}])
    engine = ReplanningEngine(provider, max_replans=1)
    decision = engine.decide("x", ActionPlan(goal="x"), [], Action(action="navigate"), ["search"], 1)
    assert decision.decision == "done"


def test_replanned_action_must_exist_before_execution():
    registry = CapabilityRegistry()
    registry.register(Capability(name="search", description="search", supported_actions={"search"}, status=CapabilityStatus.AVAILABLE, handler=None))
    assert registry.get_capability_for_action("search") is not None
    assert registry.get_capability_for_action("delete_everything") is None


def test_agent_execution_path_uses_bounded_replan():
    from advi.brain.agent import ADVIAgent
    from advi.brain.task_state import ActiveTask
    from advi.core.action_plan import Action, ActionPlan, ExecutionResult
    from advi.capabilities.registry import Capability, CapabilityRegistry, CapabilityStatus

    class FakeExecutionEngine:
        def __init__(self):
            self.calls = 0

        def execute_plan(self, plan):
            self.calls += 1
            action = plan.actions[0]
            if self.calls == 1:
                return [ExecutionResult(action=action.action, success=False, error="target missing")]
            return [ExecutionResult(action=action.action, success=True, verified=True)]

    class FakeReplanner:
        def __init__(self):
            self.calls = 0

        def decide(self, **kwargs):
            self.calls += 1
            return type("Decision", (), {
                "decision": "replan",
                "action": Action(action="focus_window"),
                "reason": "recover via window focus",
                "await_user": False,
            })()

    provider = FakeProvider([{}])
    registry = CapabilityRegistry()
    registry.register(
        Capability(
            name="desktop",
            description="desktop",
            supported_actions={"focus_window", "navigate"},
            status=CapabilityStatus.AVAILABLE,
            handler=None,
        )
    )
    engine = FakeExecutionEngine()
    agent = ADVIAgent(provider, execution_engine=engine, registry=registry)
    agent.replanner = FakeReplanner()
    task = ActiveTask(goal="focus the window")
    plan = ActionPlan(goal="focus the window", actions=[Action(action="navigate")])

    results = agent._execute_with_replanning(task, plan, "focus the window")

    assert engine.calls == 2
    assert agent.replanner.calls == 1
    assert [r.action for r in results] == ["navigate", "focus_window"]
    assert task.status.value == "completed"
