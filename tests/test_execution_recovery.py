from __future__ import annotations

from types import SimpleNamespace

from advi.core.action_plan import Action, ActionPlan, ExecutionResult, PlanStatus
from advi.core.execution_engine import ExecutionEngine
from advi.core.execution_recovery import ExecutionObserver, ExecutionRecoveryPolicy, StepObservation
from advi.capabilities.registry import Capability, CapabilityRegistry, CapabilityStatus


class FakeHandler:
    def __init__(self, results):
        self.results = iter(results)
        self.context = None

    def execute(self, action):
        return next(self.results)


class PassthroughVerifier:
    def verify(self, action, result):
        return result


class RecordingObserver(ExecutionObserver):
    def __init__(self):
        self.items = []

    def after_step(self, observation: StepObservation) -> None:
        self.items.append(observation)


def make_engine(action: str, results: list[ExecutionResult], observer=None, max_retries=1):
    registry = CapabilityRegistry()
    registry.register(
        Capability(
            name="fake",
            description="fake",
            supported_actions={action},
            status=CapabilityStatus.AVAILABLE,
            handler=FakeHandler(results),
        )
    )
    return ExecutionEngine(
        registry=registry,
        verifier=PassthroughVerifier(),
        observer=observer,
        recovery_policy=ExecutionRecoveryPolicy(),
        max_retries_per_action=max_retries,
    )


def test_transient_safe_failure_is_retried_and_final_result_returned():
    observer = RecordingObserver()
    engine = make_engine(
        "navigate",
        [
            ExecutionResult(action="navigate", success=False, error="Connection temporarily unavailable"),
            ExecutionResult(action="navigate", success=True, verified=True, data="https://example.com"),
        ],
        observer=observer,
    )

    plan = ActionPlan(goal="open site", actions=[Action(action="navigate", parameters={"url": "https://example.com"})])
    results = engine.execute_plan(plan)

    assert plan.status == PlanStatus.SUCCESS
    assert len(results) == 1
    assert results[0].success is True
    assert results[0].metadata["recovered"] is True
    assert results[0].metadata["recovery_attempts"] == 1
    assert len(observer.items) == 2
    assert observer.items[0].success is False
    assert observer.items[1].success is True


def test_side_effecting_action_is_not_automatically_retried():
    observer = RecordingObserver()
    engine = make_engine(
        "type_text",
        [ExecutionResult(action="type_text", success=False, error="Connection temporarily unavailable")],
        observer=observer,
    )

    plan = ActionPlan(goal="type hello", actions=[Action(action="type_text", parameters={"value": "hello"})])
    results = engine.execute_plan(plan)

    assert plan.status == PlanStatus.FAILURE
    assert len(results) == 1
    assert results[0].success is False
    assert len(observer.items) == 1


def test_unverified_success_does_not_trigger_retry():
    observer = RecordingObserver()
    engine = make_engine(
        "navigate",
        [ExecutionResult(action="navigate", success=True, verified=False, error=None)],
        observer=observer,
    )

    plan = ActionPlan(goal="navigate", actions=[Action(action="navigate", parameters={"url": "https://example.com"})])
    results = engine.execute_plan(plan)

    assert plan.status == PlanStatus.SUCCESS
    assert len(results) == 1
    assert results[0].success is True
    assert results[0].verified is False
    assert len(observer.items) == 1
