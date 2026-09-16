from types import SimpleNamespace

from advi.brain.agent import ADVIAgent
from advi.brain.conversation_state import ConversationState
from advi.core.action_plan import ActionPlan, ExecutionResult, Action, VerificationStatus
from advi.core.diagnostics import DiagnosticsCollector
from advi.capabilities.registry import Capability, CapabilityRegistry, CapabilityStatus


class _Provider:
    def generate(self, prompt):
        raise AssertionError("LLM should not be called in diagnostics tests")


class _Executor:
    def execute_action(self, action):
        return ExecutionResult(action=action.action, success=True, verified=True, verification_status=VerificationStatus.VERIFIED)


class _Fallback:
    def available(self):
        return True


def _agent():
    registry = CapabilityRegistry()
    registry.register(
        Capability(
            name="files",
            description="file operations",
            supported_actions={"read_file"},
            status=CapabilityStatus.AVAILABLE,
            handler=lambda action: None,
        )
    )
    return ADVIAgent(
        provider=_Provider(),
        execution_engine=_Executor(),
        registry=registry,
        fallback_gateway=_Fallback(),
        resume_task=False,
    )


def test_diagnostics_is_json_safe_and_bounded():
    agent = _agent()
    result = ExecutionResult(
        action="read_file",
        success=False,
        error="temporary",
        verified=False,
        verification_status=VerificationStatus.FAILED,
        metadata={"failure_class": "transient"},
    )
    agent.conversation_state.add_results([result])

    snapshot = agent.diagnostics()

    assert snapshot["pending_confirmation"] is False
    assert snapshot["recent_results"][0]["action"] == "read_file"
    assert snapshot["recent_results"][0]["failure_class"] == "transient"
    assert snapshot["capability_summary"][0]["name"] == "files"
    assert snapshot["runtime_flags"]["fallback_available"] is True


def test_diagnostics_reports_task_recovery_state():
    agent = _agent()
    agent.conversation_state.current_task = SimpleNamespace(
        task_id="task-1",
        goal="recover",
        status=SimpleNamespace(value="IN_PROGRESS"),
        context={"_replan_count": 2, "_last_failure_class": "environment"},
        to_dict=lambda: {"task_id": "task-1", "status": "IN_PROGRESS", "context": {"_replan_count": 2}},
    )

    snapshot = DiagnosticsCollector().capture(agent).to_dict()

    assert snapshot["active_task"]["task_id"] == "task-1"
    assert snapshot["runtime_flags"]["replan_count"] == 2
    assert snapshot["runtime_flags"]["last_failure_class"] == "environment"
