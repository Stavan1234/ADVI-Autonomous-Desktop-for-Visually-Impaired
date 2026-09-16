from types import SimpleNamespace

from advi.core.health import HealthCheck, HealthReport, HealthStatus
from advi.core.startup_health import StartupHealthValidator


def _report(*checks):
    return HealthReport(status=HealthStatus.HEALTHY, checks=list(checks))


def test_startup_ready_when_all_checks_healthy():
    result = StartupHealthValidator().validate(_report(
        HealthCheck("runtime", HealthStatus.HEALTHY, "ok"),
        HealthCheck("provider", HealthStatus.HEALTHY, "ok"),
        HealthCheck("capabilities", HealthStatus.HEALTHY, "ok"),
    ))
    assert result.state == "ready"
    assert result.ready is True


def test_startup_allows_degraded_optional_capabilities():
    report = _report(
        HealthCheck("runtime", HealthStatus.HEALTHY, "ok"),
        HealthCheck("provider", HealthStatus.HEALTHY, "ok"),
        HealthCheck("capabilities", HealthStatus.DEGRADED, "browser unavailable"),
    )
    result = StartupHealthValidator().validate(report)
    assert result.state == "degraded"
    assert result.ready is True
    assert "capabilities" in result.degraded_checks


def test_startup_blocks_unhealthy_provider():
    report = _report(
        HealthCheck("runtime", HealthStatus.HEALTHY, "ok"),
        HealthCheck("provider", HealthStatus.UNHEALTHY, "provider failed"),
    )
    result = StartupHealthValidator().validate(report)
    assert result.state == "not_ready"
    assert result.ready is False
    assert result.blocking_checks == ["provider"]


def test_startup_blocks_inconsistent_task_state():
    report = _report(
        HealthCheck("runtime", HealthStatus.HEALTHY, "ok"),
        HealthCheck("provider", HealthStatus.HEALTHY, "ok"),
        HealthCheck("task_state", HealthStatus.UNHEALTHY, "invalid state"),
    )
    result = StartupHealthValidator().validate(report)
    assert result.state == "not_ready"
    assert "task_state" in result.blocking_checks


def test_startup_never_treats_unknown_as_fully_healthy():
    report = _report(
        HealthCheck("runtime", HealthStatus.HEALTHY, "ok"),
        HealthCheck("provider", HealthStatus.HEALTHY, "ok"),
        HealthCheck("fallback", HealthStatus.UNKNOWN, "unknown"),
    )
    result = StartupHealthValidator().validate(report)
    assert result.state == "degraded"
    assert result.ready is True
