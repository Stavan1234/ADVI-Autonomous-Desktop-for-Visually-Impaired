from advi.core.action_plan import Action, ExecutionResult, VerificationStatus
from advi.core.failure_classification import FailureClass, FailureClassifier
from advi.core.execution_recovery import ExecutionRecoveryPolicy


def result(**kwargs):
    return ExecutionResult(action="test", success=False, **kwargs)


def test_classifies_invalid_input():
    c=FailureClassifier()
    assert c.classify(Action(action="save_file"), result(error="Invalid action parameters: missing required 'path'")) == FailureClass.INVALID_INPUT


def test_classifies_unavailable_capability():
    c=FailureClassifier()
    assert c.classify(Action(action="x"), result(error="No capability registered for action 'x'.")) == FailureClass.UNAVAILABLE_CAPABILITY


def test_classifies_permission_denial():
    c=FailureClassifier()
    assert c.classify(Action(action="delete_file"), result(error="Permission denied")) == FailureClass.PERMISSION_DENIED


def test_classifies_transient():
    c=FailureClassifier()
    assert c.classify(Action(action="navigate"), result(error="Connection timed out")) == FailureClass.TRANSIENT


def test_classifies_environment():
    c=FailureClassifier()
    assert c.classify(Action(action="click"), result(error="Cannot connect to X11 display")) == FailureClass.ENVIRONMENT


def test_classifies_verification_failure():
    c=FailureClassifier()
    r=ExecutionResult(action="save_file", success=False, verification_status=VerificationStatus.FAILED, error="file missing")
    assert c.classify(Action(action="save_file"), r) == FailureClass.VERIFICATION_FAILED


def test_annotation_adds_machine_readable_class():
    c=FailureClassifier()
    r=c.annotate(Action(action="navigate"), result(error="Connection timed out"))
    assert r.metadata["failure_class"] == FailureClass.TRANSIENT.value


def test_recovery_retries_only_transient_class():
    policy=ExecutionRecoveryPolicy()
    a=Action(action="navigate")
    transient=ExecutionResult(action="navigate", success=False, error="timeout", metadata={"failure_class":"transient"})
    denied=ExecutionResult(action="navigate", success=False, error="permission denied", metadata={"failure_class":"permission_denied"})
    assert policy.decide(a, transient, attempt=1, max_retries=1).retry is True
    assert policy.decide(a, denied, attempt=1, max_retries=1).retry is False
