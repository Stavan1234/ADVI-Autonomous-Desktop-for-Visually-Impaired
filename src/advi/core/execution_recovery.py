from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .action_plan import Action, ExecutionResult
from .failure_classification import FailureClass, FailureClassifier


@dataclass(frozen=True)
class StepObservation:
    """Structured observation captured after an execution attempt."""

    action: str
    success: bool
    verified: bool
    error: str | None = None
    data: Any = None
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RecoveryDecision:
    """Deterministic decision about what to do after an execution attempt."""

    retry: bool = False
    reason: str = ""


class ExecutionRecoveryPolicy:
    """Bounded, conservative recovery policy for the primary execution engine.

    Recovery is deliberately deterministic. It never retries an action merely because a
    verifier returned ``verified=False``; uncertain outcomes can have side effects and must
    remain visible to the caller instead of being duplicated.
    """

    # Actions whose failure is commonly transient and whose retry is comparatively safe.
    RETRYABLE_ACTIONS = frozenset({
        "open_application",
        "focus_window",
        "navigate",
        "search",
        "read_file",
        "wait",
    })

    TRANSIENT_MARKERS = (
        "temporarily",
        "timeout",
        "timed out",
        "not ready",
        "busy",
        "connection",
        "connect",
        "no such window",
        "window could not be found",
        "could not be found",
        "target could not be found",
        "target .* could not be resolved",
    )

    def decide(
        self,
        action: Action,
        result: ExecutionResult,
        *,
        attempt: int,
        max_retries: int,
    ) -> RecoveryDecision:
        failure_class = result.metadata.get("failure_class")
        if result.success or attempt > max_retries:
            return RecoveryDecision(reason="no_recovery_needed")

        if action.action not in self.RETRYABLE_ACTIONS:
            return RecoveryDecision(reason=f"action_not_retryable:{action.action}")

        if failure_class and failure_class != FailureClass.TRANSIENT.value:
            return RecoveryDecision(reason=f"failure_class:{failure_class}")
        error = (result.error or "").lower()
        if not error and not failure_class:
            return RecoveryDecision(reason="failure_has_no_error_detail")

        if failure_class == FailureClass.TRANSIENT.value:
            return RecoveryDecision(retry=True, reason="transient_execution_failure")

        classifier = FailureClassifier()
        if classifier.classify(action, result) == FailureClass.TRANSIENT:
            return RecoveryDecision(retry=True, reason="transient_execution_failure")
        return RecoveryDecision(reason="failure_not_classified_as_transient")


class ExecutionObserver:
    """Observer interface used by tests, diagnostics, and future brain-level replanning."""

    def after_step(self, observation: StepObservation) -> None:  # pragma: no cover - interface
        return None
