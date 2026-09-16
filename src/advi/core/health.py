from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .capability_readiness import CapabilityReadinessChecker
from advi.capabilities.registry import CapabilityRegistry


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class HealthCheck:
    name: str
    status: HealthStatus
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class HealthReport:
    status: HealthStatus
    checks: list[HealthCheck]

    @property
    def healthy(self) -> bool:
        return self.status == HealthStatus.HEALTHY

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "healthy": self.healthy,
            "checks": [check.to_dict() for check in self.checks],
        }


class ADVIHealthChecker:
    """Read-only runtime health checks.

    Health checks must never execute user actions. Capability availability is
    inspected from the registry's current cached state; callers may explicitly
    request a refresh when they are comfortable with probe side effects.
    """

    def __init__(self, readiness_checker: CapabilityReadinessChecker | None = None) -> None:
        self.readiness_checker = readiness_checker or CapabilityReadinessChecker()

    def check(self, agent: Any, *, refresh_capabilities: bool = False) -> HealthReport:
        checks = [
            self._runtime_check(agent),
            self._provider_check(agent),
            self._task_state_check(agent),
            self._capability_check(agent, refresh_capabilities=refresh_capabilities),
            self._persistence_check(agent),
            self._journal_check(agent),
            self._fallback_check(agent),
        ]
        statuses = [check.status for check in checks]
        if any(status == HealthStatus.UNHEALTHY for status in statuses):
            overall = HealthStatus.UNHEALTHY
        elif any(status == HealthStatus.DEGRADED for status in statuses):
            overall = HealthStatus.DEGRADED
        elif any(status == HealthStatus.UNKNOWN for status in statuses):
            overall = HealthStatus.UNKNOWN
        else:
            overall = HealthStatus.HEALTHY
        return HealthReport(overall, checks)

    @staticmethod
    def _runtime_check(agent: Any) -> HealthCheck:
        started = getattr(getattr(agent, "runtime", None), "started", None)
        if started is None:
            return HealthCheck("runtime", HealthStatus.UNKNOWN, "Runtime lifecycle state is not attached to agent.")
        return HealthCheck(
            "runtime",
            HealthStatus.HEALTHY if started else HealthStatus.UNHEALTHY,
            "Runtime is active." if started else "Runtime is not active.",
            {"started": bool(started)},
        )

    @staticmethod
    def _provider_check(agent: Any) -> HealthCheck:
        provider = getattr(agent, "provider", None)
        if provider is None:
            return HealthCheck("provider", HealthStatus.UNHEALTHY, "No LLM provider is configured.")
        attempts = list(getattr(provider, "last_attempts", ()) or ())
        failed = sum(1 for item in attempts if not getattr(item, "success", False))
        successful = next((item for item in reversed(attempts) if getattr(item, "success", False)), None)
        if failed and successful is not None:
            status = HealthStatus.DEGRADED
            message = "Primary provider had a failure; the provider chain recovered."
        elif attempts and failed == len(attempts):
            status = HealthStatus.UNHEALTHY
            message = "The last provider chain attempt failed."
        else:
            status = HealthStatus.HEALTHY
            message = "LLM provider is configured."
        return HealthCheck(
            "provider", status, message,
            {"name": getattr(provider, "name", type(provider).__name__), "attempts": [
                {
                    "provider": getattr(item, "provider", None),
                    "success": bool(getattr(item, "success", False)),
                    "error_type": getattr(item, "error_type", None),
                }
                for item in attempts[-5:]
            ]},
        )

    @staticmethod
    def _task_state_check(agent: Any) -> HealthCheck:
        state = getattr(agent, "conversation_state", None)
        if state is None:
            return HealthCheck("task_state", HealthStatus.UNHEALTHY, "Conversation state is missing.")
        task = getattr(state, "current_task", None)
        if task is None:
            return HealthCheck("task_state", HealthStatus.HEALTHY, "No active task; state is idle.")
        context = getattr(task, "context", {}) or {}
        status = getattr(getattr(task, "status", None), "value", getattr(task, "status", None))
        if status == "AWAITING_CONFIRMATION" and not getattr(task, "confirmation_fingerprint", None):
            return HealthCheck("task_state", HealthStatus.UNHEALTHY, "Task is awaiting confirmation without a bound approval fingerprint.")
        if context.get("_interrupted_step") and status != "AWAITING_INPUT":
            return HealthCheck("task_state", HealthStatus.UNHEALTHY, "Interrupted execution is recorded without a review state.")
        return HealthCheck("task_state", HealthStatus.HEALTHY, "Active task state is internally consistent.", {"status": status, "task_id": getattr(task, "task_id", None)})

    def _capability_check(self, agent: Any, *, refresh_capabilities: bool) -> HealthCheck:
        registry: CapabilityRegistry | None = getattr(agent, "registry", None)
        if registry is None:
            return HealthCheck("capabilities", HealthStatus.UNHEALTHY, "Capability registry is missing.")
        if refresh_capabilities:
            try:
                registry.refresh_stale()
            except Exception as exc:
                return HealthCheck("capabilities", HealthStatus.DEGRADED, "Capability refresh failed; using cached state.", {"error": str(exc)})
        report = self.readiness_checker.check(registry)
        unavailable = [c.name for c in registry.list_all() if not c.is_available()]
        if not report.ready:
            return HealthCheck(
                "capabilities", HealthStatus.UNHEALTHY,
                "Capability readiness audit found issues.",
                {"checked_actions": report.checked_actions, "issues": [issue.__dict__ for issue in report.issues], "unavailable": unavailable},
            )
        if unavailable:
            return HealthCheck("capabilities", HealthStatus.DEGRADED, "Some registered capabilities are unavailable.", {"unavailable": unavailable})
        return HealthCheck("capabilities", HealthStatus.HEALTHY, "Registered capabilities are ready.", {"checked_actions": report.checked_actions})

    @staticmethod
    def _persistence_check(agent: Any) -> HealthCheck:
        persistence = getattr(agent, "task_persistence", None)
        if persistence is None:
            return HealthCheck("persistence", HealthStatus.DEGRADED, "Task persistence is not configured.")
        path = getattr(persistence, "database_path", None)
        if path is None:
            return HealthCheck("persistence", HealthStatus.DEGRADED, "Task persistence has no database path.")
        try:
            with persistence._connect() as connection:
                connection.execute("SELECT 1").fetchone()
            return HealthCheck("persistence", HealthStatus.HEALTHY, "Task persistence database is reachable.")
        except Exception as exc:
            return HealthCheck("persistence", HealthStatus.UNHEALTHY, "Task persistence database is not reachable.", {"error": str(exc)})

    @staticmethod
    def _journal_check(agent: Any) -> HealthCheck:
        journal = getattr(agent, "execution_journal", None)
        if journal is None:
            return HealthCheck("execution_journal", HealthStatus.DEGRADED, "Execution journal is not configured.")
        task = getattr(getattr(agent, "conversation_state", None), "current_task", None)
        if task is None:
            return HealthCheck("execution_journal", HealthStatus.HEALTHY, "Execution journal is available.")
        plan = getattr(task, "plan", None)
        if not plan:
            return HealthCheck("execution_journal", HealthStatus.HEALTHY, "No active plan requires journal inspection.")
        try:
            interrupted = journal.interrupted_step(task.task_id, journal.fingerprint_plan(plan.goal, plan.actions))
        except Exception as exc:
            return HealthCheck("execution_journal", HealthStatus.UNHEALTHY, "Execution journal could not be inspected.", {"error": str(exc)})
        if interrupted:
            return HealthCheck("execution_journal", HealthStatus.DEGRADED, "An interrupted step requires review before replay.", {"step_index": interrupted.get("step_index"), "action": interrupted.get("action")})
        return HealthCheck("execution_journal", HealthStatus.HEALTHY, "Execution journal is consistent for the active plan.")

    @staticmethod
    def _fallback_check(agent: Any) -> HealthCheck:
        gateway = getattr(agent, "fallback_gateway", None)
        if gateway is None:
            return HealthCheck("fallback", HealthStatus.DEGRADED, "David fallback is not configured.", {"available": False})
        try:
            available = bool(gateway.available())
        except Exception as exc:
            return HealthCheck("fallback", HealthStatus.UNKNOWN, "Fallback availability could not be determined.", {"error": str(exc)})
        return HealthCheck("fallback", HealthStatus.HEALTHY if available else HealthStatus.DEGRADED, "David fallback is available." if available else "David fallback is unavailable.", {"available": available})


__all__ = ["HealthStatus", "HealthCheck", "HealthReport", "ADVIHealthChecker"]
