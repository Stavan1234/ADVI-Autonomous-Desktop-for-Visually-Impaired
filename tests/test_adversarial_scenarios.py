import json
from pathlib import Path
from types import SimpleNamespace

from advi.brain.fallback_policy import FallbackPolicy
from advi.core.action_plan import Action, ActionPlan, ExecutionResult, VerificationStatus
from advi.core.confirmation import ConfirmationManager
from advi.core.failure_classification import FailureClass, FailureClassifier
from advi.core.execution_recovery import ExecutionRecoveryPolicy
from advi.core.goal_verification import GoalVerifier, GoalVerificationStatus
from advi.core.replanning import ReplanningEngine
from advi.core.structured_output import parse_structured_output


def test_transient_timeout_is_retryable_once():
    policy = ExecutionRecoveryPolicy()
    action = Action(action="navigate", parameters={"url": "https://example.com"})
    result = ExecutionResult(action="navigate", success=False, error="Connection timed out", metadata={"failure_class": "transient"})
    assert policy.decide(action, result, attempt=1, max_retries=1).retry
    assert not policy.decide(action, result, attempt=2, max_retries=1).retry


def test_side_effecting_failure_is_not_automatically_retried():
    policy = ExecutionRecoveryPolicy()
    action = Action(action="save_file", parameters={"path": "x.txt", "text": "hello"})
    result = ExecutionResult(action="save_file", success=False, error="timeout", metadata={"failure_class": "transient"})
    assert not policy.decide(action, result, attempt=1, max_retries=1).retry


def test_malformed_plan_action_is_rejected_before_executor():
    from advi.core.action_contracts import validate_and_normalize_action
    action = Action(action="save_file", parameters={"text": "hello"})
    normalized, errors = validate_and_normalize_action(action)
    assert normalized is None
    assert errors


def test_unavailable_capability_is_not_retried_or_hidden():
    classifier = FailureClassifier()
    action = Action(action="search")
    result = ExecutionResult(action="search", success=False, error="No capability registered for action 'search'.")
    assert classifier.classify(action, result) == FailureClass.UNAVAILABLE_CAPABILITY
    assert not ExecutionRecoveryPolicy().decide(action, result, attempt=1, max_retries=1).retry


def test_permission_failure_never_goes_to_david():
    decision = FallbackPolicy().decide(FailureClass.PERMISSION_DENIED, gateway_available=True)
    assert not decision.use_fallback


def test_partial_effects_block_automatic_david_handoff():
    decision = FallbackPolicy().decide(
        FailureClass.ENVIRONMENT,
        gateway_available=True,
        partial_results=True,
    )
    assert not decision.use_fallback
    assert "effects" in decision.reason


def test_verification_failure_is_distinct_from_execution_failure():
    result = ExecutionResult(
        action="save_file",
        success=False,
        error="file missing after save",
        verification_status=VerificationStatus.FAILED,
    )
    classified = FailureClassifier().classify(Action(action="save_file"), result)
    assert classified == FailureClass.VERIFICATION_FAILED


def test_uncertain_goal_is_not_reported_as_verified():
    plan = ActionPlan(goal="do something", actions=[Action(action="open_application")])
    result = ExecutionResult(action="open_application", success=True)
    evidence = GoalVerifier().verify(plan, [result])
    assert evidence.status == GoalVerificationStatus.UNCERTAIN
    assert not evidence.verified


def test_stale_confirmation_is_rejected(monkeypatch):
    manager = ConfirmationManager(ttl_seconds=5)
    plan = ActionPlan(goal="send email", actions=[Action(action="email_send", parameters={"to": "a@example.com"})])
    record = manager.issue(plan)
    monkeypatch.setattr("advi.core.confirmation.time.time", lambda: record.expires_at + 1)
    assert not manager.validate(plan, record.fingerprint, issued_at=record.issued_at, expires_at=record.expires_at)


def test_confirmation_is_single_use():
    manager = ConfirmationManager()
    plan = ActionPlan(goal="send email", actions=[Action(action="email_send", parameters={"to": "a@example.com"})])
    record = manager.issue(plan)
    assert manager.validate(plan, record.fingerprint, issued_at=record.issued_at, expires_at=record.expires_at)
    assert manager.consume(record.fingerprint)
    assert not manager.validate(plan, record.fingerprint, issued_at=record.issued_at, expires_at=record.expires_at)


def test_plan_change_invalidates_confirmation():
    manager = ConfirmationManager()
    original = ActionPlan(goal="send email", actions=[Action(action="email_send", parameters={"to": "a@example.com"})])
    changed = ActionPlan(goal="send email", actions=[Action(action="email_send", parameters={"to": "b@example.com"})])
    record = manager.issue(original)
    assert not manager.validate(changed, record.fingerprint, issued_at=record.issued_at, expires_at=record.expires_at)


def test_replanner_stops_at_bound_even_if_provider_keeps_replanning():
    class Provider:
        def structured(self, messages, schema):
            payload = {"decision": "replan", "reason": "try again", "action": {"action": "search", "parameters": {"query": "x"}}}
            return SimpleNamespace(text=json.dumps(payload))

    engine = ReplanningEngine(Provider(), max_replans=2)
    plan = ActionPlan(goal="search", actions=[Action(action="search", parameters={"query": "x"})])
    failure = ExecutionResult(action="search", success=False, error="timeout")
    first = engine.decide("search", plan, [failure], plan.actions[0], ["search"], 0)
    second = engine.decide("search", plan, [failure], plan.actions[0], ["search"], 2)
    assert first.decision == "replan"
    assert second.decision == "done"


def test_structured_output_malformed_payload_fails_deterministically():
    from advi.core.structured_output import StructuredOutputError
    with __import__("pytest").raises(StructuredOutputError):
        parse_structured_output("not json", {"type": "object", "required": ["mode"]})


def test_crash_state_is_not_auto_replayed(tmp_path: Path):
    from advi.core.execution_journal import ExecutionJournal
    action = Action(action="save_file", parameters={"path": str(tmp_path / "x.txt"), "text": "hello"})
    plan = ActionPlan(goal="save", actions=[action])
    journal = ExecutionJournal(tmp_path / "journal.db")
    fingerprint = journal.fingerprint_plan(plan.goal, plan.actions)
    journal.begin("task-1", fingerprint, 0, action)
    assert journal.interrupted_step("task-1", fingerprint) is not None
    journal.finish("task-1", fingerprint, 0, ExecutionResult(action="save_file", success=False, error="crashed"))
    assert journal.interrupted_step("task-1", fingerprint) is None
