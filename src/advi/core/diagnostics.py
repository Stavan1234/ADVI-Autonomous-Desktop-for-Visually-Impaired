from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class DiagnosticSnapshot:
    """Read-only runtime snapshot for debugging and health inspection."""

    captured_at: str
    active_task: dict[str, Any] | None
    recent_tasks: list[dict[str, Any]]
    recent_results: list[dict[str, Any]]
    pending_confirmation: bool
    capability_summary: list[dict[str, Any]]
    runtime_flags: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "captured_at": self.captured_at,
            "active_task": self.active_task,
            "recent_tasks": self.recent_tasks,
            "recent_results": self.recent_results,
            "pending_confirmation": self.pending_confirmation,
            "capability_summary": self.capability_summary,
            "runtime_flags": self.runtime_flags,
        }


class DiagnosticsCollector:
    """Build a bounded, JSON-safe view of an ADVIAgent runtime state."""

    def __init__(self, *, result_limit: int = 10, task_limit: int = 5) -> None:
        self.result_limit = max(1, int(result_limit))
        self.task_limit = max(1, int(task_limit))

    def capture(self, agent: Any) -> DiagnosticSnapshot:
        state = getattr(agent, "conversation_state", None)
        active = getattr(state, "current_task", None)

        recent_tasks: list[dict[str, Any]] = []
        if state is not None:
            for task in getattr(state, "recent_tasks", [])[-self.task_limit :]:
                recent_tasks.append(self._task_dict(task))

        recent_results: list[dict[str, Any]] = []
        if state is not None:
            for result in getattr(state, "recent_results", [])[-self.result_limit :]:
                recent_results.append(self._result_dict(result))

        registry = getattr(agent, "registry", None)
        capability_summary: list[dict[str, Any]] = []
        if registry is not None:
            try:
                for capability in registry.list_all():
                    capability_summary.append(
                        {
                            "name": getattr(capability, "name", None),
                            "available": getattr(capability, "available", None),
                            "availability_reason": getattr(capability, "availability_reason", None),
                            "supported_actions": list(getattr(capability, "supported_actions", []) or []),
                        }
                    )
            except Exception:
                # Diagnostics must never break the assistant.
                capability_summary = []

        runtime_flags = {
            "resumed_task": bool(getattr(state, "resumed_task", False)) if state is not None else False,
            "turn_count": int(getattr(state, "turn_count", 0)) if state is not None else 0,
            "fallback_available": bool(
                getattr(agent, "fallback_gateway", None)
                and agent.fallback_gateway.available()
            ),
            "replan_count": self._replan_count(active),
            "last_failure_class": self._last_failure_class(active),
        }

        return DiagnosticSnapshot(
            captured_at=datetime.now(timezone.utc).isoformat(),
            active_task=self._task_dict(active) if active is not None else None,
            recent_tasks=recent_tasks,
            recent_results=recent_results,
            pending_confirmation=bool(
                active is not None
                and getattr(active, "status", None) is not None
                and getattr(active.status, "value", active.status) == "AWAITING_CONFIRMATION"
            ),
            capability_summary=capability_summary,
            runtime_flags=runtime_flags,
        )

    @staticmethod
    def _task_dict(task: Any) -> dict[str, Any]:
        if task is None:
            return {}
        if hasattr(task, "to_dict"):
            try:
                return dict(task.to_dict())
            except Exception:
                pass
        return {
            "task_id": getattr(task, "task_id", None),
            "goal": getattr(task, "goal", None),
            "status": getattr(getattr(task, "status", None), "value", getattr(task, "status", None)),
        }

    @staticmethod
    def _result_dict(result: Any) -> dict[str, Any]:
        if isinstance(result, dict):
            return {
                "action": result.get("action"),
                "success": result.get("success"),
                "verified": result.get("verified"),
                "verification_status": result.get("verification_status"),
                "error": result.get("error"),
                "human_readable": result.get("human_readable"),
                "failure_class": (result.get("metadata") or {}).get("failure_class"),
            }
        return {
            "action": getattr(result, "action", None),
            "success": getattr(result, "success", None),
            "verified": getattr(result, "verified", None),
            "verification_status": getattr(getattr(result, "verification_status", None), "value", getattr(result, "verification_status", None)),
            "error": getattr(result, "error", None),
            "human_readable": getattr(result, "human_readable", None),
            "failure_class": ((getattr(result, "metadata", None) or {}).get("failure_class")),
        }

    @staticmethod
    def _replan_count(task: Any) -> int:
        if task is None:
            return 0
        try:
            return int((getattr(task, "context", {}) or {}).get("_replan_count", 0))
        except Exception:
            return 0

    @staticmethod
    def _last_failure_class(task: Any) -> str | None:
        if task is None:
            return None
        value = (getattr(task, "context", {}) or {}).get("_last_failure_class")
        return str(value) if value else None
