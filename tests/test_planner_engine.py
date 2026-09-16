from __future__ import annotations

import json

from advi.brain.planner import PlannerEngine, PlanningHints
from advi.core.action_plan import ActionPlan
from advi.capabilities.registry import Capability, CapabilityRegistry, CapabilityStatus
from advi.providers import LLMResponse


class FakeProvider:
    name = "fake"
    model = "fake"

    def __init__(self, payload):
        self.payload = payload
        self.prompts = []

    def structured(self, messages, schema):
        self.prompts.append(messages[0]["content"])
        return LLMResponse(text=json.dumps(self.payload), provider=self.name, model=self.model)


def registry_with(*actions: str) -> CapabilityRegistry:
    registry = CapabilityRegistry()
    registry.register(
        Capability(
            name="test",
            description="test capability",
            supported_actions=set(actions),
            status=CapabilityStatus.AVAILABLE,
        )
    )
    return registry


class Context:
    def format_prompt_context(self):
        return "CURRENT TASK: create a file"


def test_planner_uses_registry_and_normalizes_plan():
    provider = FakeProvider({
        "goal": "create file",
        "reason": "save the requested content",
        "missing_information": [],
        "confirmation_required": False,
        "actions": [
            {"action": "save_file", "parameters": {"path": "x.txt", "content": "hi"}},
            {"action": "delete_everything", "parameters": {}},
        ],
    })
    engine = PlannerEngine(provider, registry_with("save_file"))
    plan = engine.plan("create file", Context())
    assert isinstance(plan, ActionPlan)
    assert [a.action for a in plan.actions] == ["save_file"]
    assert "delete_everything" in plan.reason


def test_planner_receives_reasoning_hints():
    provider = FakeProvider({
        "goal": "search",
        "reason": "use search",
        "missing_information": [],
        "confirmation_required": False,
        "actions": [{"action": "search", "parameters": {"query": "OpenAI"}}],
    })
    engine = PlannerEngine(provider, registry_with("search"))
    engine.plan(
        "search",
        Context(),
        PlanningHints(preferred_action="search", reason="reasoning selected search", references={"target": "web"}),
    )
    prompt = provider.prompts[0]
    assert "preferred_action: search" in prompt
    assert "reasoning selected search" in prompt
    assert '"target": "web"' in prompt


def test_planner_does_not_require_finish_action():
    provider = FakeProvider({
        "goal": "read",
        "missing_information": [],
        "confirmation_required": False,
        "actions": [{"action": "read_file", "parameters": {"path": "x.txt"}}],
    })
    engine = PlannerEngine(provider, registry_with("read_file"))
    plan = engine.plan("read", Context())
    assert [a.action for a in plan.actions] == ["read_file"]


def test_planner_failure_returns_empty_plan():
    class BrokenProvider(FakeProvider):
        def structured(self, messages, schema):
            raise RuntimeError("model down")

    engine = PlannerEngine(BrokenProvider({}), registry_with("search"))
    plan = engine.plan("search", Context())
    assert plan.actions == []
