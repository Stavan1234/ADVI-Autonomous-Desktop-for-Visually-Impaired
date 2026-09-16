from types import SimpleNamespace

from advi.brain.agent import ADVIAgent
from advi.capabilities.registry import Capability, CapabilityRegistry, CapabilityStatus
from advi.core.action_plan import ExecutionResult
from advi.core.health import ADVIHealthChecker, HealthStatus


class _Provider:
    name = "test"
    model = "test"
    last_attempts = ()
    def generate(self, prompt):
        raise AssertionError("LLM should not be called")


class _Executor:
    def execute_action(self, action):
        return ExecutionResult(action=action.action, success=True, verified=True)


class _Fallback:
    def available(self):
        return True


def _registry():
    registry = CapabilityRegistry()
    registry.register(Capability(
        name="files",
        description="file operations",
        supported_actions={"read_file"},
        status=CapabilityStatus.AVAILABLE,
        handler=SimpleNamespace(execute=lambda action: None),
    ))
    return registry


def _agent():
    return ADVIAgent(
        provider=_Provider(),
        execution_engine=_Executor(),
        registry=_registry(),
        fallback_gateway=_Fallback(),
        resume_task=False,
    )


def test_health_is_read_only_and_reports_healthy_core():
    agent = _agent()
    report = agent.health()
    assert report["status"] == HealthStatus.DEGRADED.value  # persistence is intentionally not configured
    names = {check["name"] for check in report["checks"]}
    assert {"runtime", "provider", "task_state", "capabilities", "persistence", "execution_journal", "fallback"} <= names


def test_unavailable_capability_degrades_health_without_executing_anything():
    registry = _registry()
    registry.set_status("files", CapabilityStatus.UNAVAILABLE, reason="test outage")
    agent = ADVIAgent(provider=_Provider(), execution_engine=_Executor(), registry=registry, fallback_gateway=_Fallback(), resume_task=False)
    report = ADVIHealthChecker().check(agent)
    capability = next(item for item in report.checks if item.name == "capabilities")
    assert capability.status == HealthStatus.DEGRADED
    assert "files" in capability.details["unavailable"]


def test_confirmation_without_fingerprint_is_unhealthy():
    agent = _agent()
    task = SimpleNamespace(
        task_id="task-1",
        plan=None,
        status=SimpleNamespace(value="AWAITING_CONFIRMATION"),
        confirmation_fingerprint=None,
        context={},
    )
    agent.conversation_state.current_task = task
    report = ADVIHealthChecker().check(agent)
    task_check = next(item for item in report.checks if item.name == "task_state")
    assert task_check.status == HealthStatus.UNHEALTHY
