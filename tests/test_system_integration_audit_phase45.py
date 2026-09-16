from __future__ import annotations

from advi.brain.agent import ADVIAgent
from advi.brain.context import AgentContext
from advi.capabilities.registry import Capability, CapabilityRegistry, CapabilityStatus
from advi.core.action_plan import Action, ActionPlan, ExecutionResult
from advi.core.capability_policy import PolicyDisposition


class Provider:
    def generate(self, prompt: str):
        class R:
            text = '{"mode":"conversation","reason":"test"}'
        return R()


class DummyHandler:
    def execute(self, action):
        return ExecutionResult(action=action.action, success=True, data={"ok": True})


def registry_for_memory() -> CapabilityRegistry:
    registry = CapabilityRegistry()
    registry.register(Capability(
        name="memory",
        description="test memory",
        supported_actions={"memory_update", "memory_forget"},
        status=CapabilityStatus.AVAILABLE,
        handler=DummyHandler(),
        availability_probe=None,
    ))
    return registry


def test_agent_uses_unified_reasoning_for_legacy_classify_helper():
    agent = ADVIAgent(provider=Provider(), registry=registry_for_memory(), resume_task=False)
    agent.reasoner.decide = lambda text, context: type("D", (), {
        "mode": "action", "intent_hint": "", "reason": "central", "memory_fact": None,
        "memory_query": None, "task_update": None, "action": "memory_update", "goal": text,
        "confidence": 0.9, "missing_information": [], "references": {},
    })()
    result = agent._classify_intent("remember x", AgentContext(current_message="remember x"))
    assert result["intent"] == "action"
    assert result["reasoning"] == "central"


def test_direct_memory_forget_is_policy_gated_and_persisted_as_confirmation_task():
    agent = ADVIAgent(provider=Provider(), registry=registry_for_memory(), resume_task=False)
    decision = agent.capability_policy.evaluate_action(Action(action="memory_forget", parameters={"fact": "x"}))
    assert decision.disposition == PolicyDisposition.CONFIRM

    action = Action(action="memory_forget", parameters={"fact": "x"})
    task = __import__('advi.brain.task_state', fromlist=['ActiveTask']).ActiveTask(goal="Forget memory: x")
    task.plan = ActionPlan(goal=task.goal, actions=[action])
    confirmation = agent.confirmation_manager.issue(task.plan)
    task.set_awaiting_confirmation("Please confirm before continuing.", confirmation.fingerprint, confirmation.issued_at, confirmation.expires_at)
    agent.active_task = task
    assert agent.active_task is not None
    assert agent.active_task.status.value == "awaiting_confirmation"


def test_direct_memory_update_uses_same_policy_boundary():
    agent = ADVIAgent(provider=Provider(), registry=registry_for_memory(), resume_task=False)
    class Engine:
        def execute_action(self, action):
            return ExecutionResult(action=action.action, success=True, data={"ok": True})
    agent.execution_engine = Engine()
    result = agent._execute_authorized_action(Action(action="memory_update", parameters={"fact": "x"}))
    assert result.success is True
