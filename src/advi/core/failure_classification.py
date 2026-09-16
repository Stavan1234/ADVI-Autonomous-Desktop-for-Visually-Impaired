from __future__ import annotations

from enum import Enum
from typing import Any

from .action_plan import Action, ExecutionResult


class FailureClass(str, Enum):
    SUCCESS = "success"
    INVALID_INPUT = "invalid_input"
    UNAVAILABLE_CAPABILITY = "unavailable_capability"
    PERMISSION_DENIED = "permission_denied"
    TRANSIENT = "transient"
    ENVIRONMENT = "environment"
    VERIFICATION_FAILED = "verification_failed"
    TASK_FAILED = "task_failed"
    UNKNOWN = "unknown"


class FailureClassifier:
    """Deterministically classify execution outcomes for recovery/routing."""

    TRANSIENT_MARKERS = (
        "temporarily", "timeout", "timed out", "busy", "not ready",
        "connection reset", "connection refused", "connection error",
        "could not find", "not found", "no such window",
    )
    PERMISSION_MARKERS = (
        "permission denied", "access denied", "not authorized", "unauthorized",
        "forbidden", "requires confirmation", "confirmation required",
    )
    INPUT_MARKERS = (
        "invalid action parameters", "missing required", "invalid parameter",
        "must be a", "cannot be empty", "expected a ",
    )
    UNAVAILABLE_MARKERS = (
        "no capability registered", "capability .* unavailable",
        "capability handler", "is currently unavailable",
    )
    ENVIRONMENT_MARKERS = (
        "display", "x11", "cannot connect to", "cdp", "browser is not running",
        "file system", "os error", "win32", "desktop context",
    )

    def classify(self, action: Action, result: ExecutionResult) -> FailureClass:
        if result.success and result.verification_status.value == "verified":
            return FailureClass.SUCCESS
        if result.verification_status.value == "failed":
            return FailureClass.VERIFICATION_FAILED

        error = (result.error or "").strip().lower()
        if not error:
            return FailureClass.UNKNOWN if not result.success else FailureClass.SUCCESS

        if any(m in error for m in self.INPUT_MARKERS):
            return FailureClass.INVALID_INPUT
        if any(m in error for m in self.PERMISSION_MARKERS):
            return FailureClass.PERMISSION_DENIED
        if "no capability registered" in error or "currently unavailable" in error or "capability handler" in error:
            return FailureClass.UNAVAILABLE_CAPABILITY
        if any(m in error for m in self.TRANSIENT_MARKERS):
            return FailureClass.TRANSIENT
        if any(m in error for m in self.ENVIRONMENT_MARKERS):
            return FailureClass.ENVIRONMENT
        return FailureClass.TASK_FAILED

    def annotate(self, action: Action, result: ExecutionResult) -> ExecutionResult:
        failure_class = self.classify(action, result)
        metadata = {**result.metadata, "failure_class": failure_class.value}
        return result.model_copy(update={"metadata": metadata})
