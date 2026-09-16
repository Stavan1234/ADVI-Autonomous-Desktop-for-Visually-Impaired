from types import SimpleNamespace

from advi.brain.fallback_gateway import DavidFallbackGateway
from advi.brain.fallback_policy import FallbackPolicy
from advi.core.failure_classification import FailureClass


def test_unavailable_capability_routes_to_david():
    d = FallbackPolicy().decide(FailureClass.UNAVAILABLE_CAPABILITY, gateway_available=True)
    assert d.use_fallback


def test_environment_routes_to_david():
    d = FallbackPolicy().decide(FailureClass.ENVIRONMENT, gateway_available=True)
    assert d.use_fallback


def test_permission_denied_never_routes_to_david():
    d = FallbackPolicy().decide(FailureClass.PERMISSION_DENIED, gateway_available=True)
    assert not d.use_fallback


def test_invalid_input_never_routes_to_david():
    d = FallbackPolicy().decide(FailureClass.INVALID_INPUT, gateway_available=True)
    assert not d.use_fallback


def test_task_failure_does_not_auto_fallback():
    d = FallbackPolicy().decide(FailureClass.TASK_FAILED, gateway_available=True)
    assert not d.use_fallback


def test_string_failure_class_is_supported():
    d = FallbackPolicy().decide(FailureClass.ENVIRONMENT.value, gateway_available=True)
    assert d.use_fallback


def test_david_gateway_translates_service_result():
    service = SimpleNamespace(
        process=lambda _text: SimpleNamespace(success=True, results=[], text="David handled it."),
    )
    outcome = DavidFallbackGateway(service).process("hello", reason="environment")
    assert outcome.success is True
    assert outcome.text == "David handled it."


def test_david_gateway_handles_service_error():
    service = SimpleNamespace(process=lambda _text: (_ for _ in ()).throw(RuntimeError("boom")))
    outcome = DavidFallbackGateway(service).process("hello")
    assert outcome.success is False
    assert "David fallback failed" in outcome.reason
