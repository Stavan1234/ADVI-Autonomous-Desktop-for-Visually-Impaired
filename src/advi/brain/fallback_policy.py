from __future__ import annotations

from dataclasses import dataclass
from .fallback_gateway import FallbackGateway
from advi.core.failure_classification import FailureClass


@dataclass(frozen=True)
class FallbackDecision:
    use_fallback: bool
    reason: str


class FallbackPolicy:
    """Conservative routing policy between ADVI and David."""

    # These indicate the primary capability path itself is unavailable or
    # blocked by the environment. They are the safest automatic hand-off cases.
    AUTO_FALLBACK_CLASSES = frozenset({
        FailureClass.UNAVAILABLE_CAPABILITY,
        FailureClass.ENVIRONMENT,
    })

    NEVER_FALLBACK_CLASSES = frozenset({
        FailureClass.INVALID_INPUT,
        FailureClass.PERMISSION_DENIED,
    })

    def decide(
        self,
        failure_class: FailureClass | str | None,
        *,
        gateway_available: bool,
        partial_results: bool = False,
        handoff_safe: bool = False,
    ) -> FallbackDecision:
        if not gateway_available:
            return FallbackDecision(False, "David fallback unavailable")
        if isinstance(failure_class, FailureClass):
            failure = failure_class
        else:
            try:
                failure = FailureClass(str(failure_class)) if failure_class is not None else FailureClass.UNKNOWN
            except ValueError:
                failure = FailureClass.UNKNOWN

        if failure in self.NEVER_FALLBACK_CLASSES:
            return FallbackDecision(False, f"{failure.value} requires correction or user action")
        if partial_results and not handoff_safe:
            return FallbackDecision(False, "Primary execution already produced effects; automatic David hand-off is unsafe")
        if failure in self.AUTO_FALLBACK_CLASSES:
            suffix = " after partial primary execution" if partial_results else ""
            return FallbackDecision(True, f"{failure.value} indicates primary route is unavailable{suffix}")

        return FallbackDecision(False, f"{failure.value} is not safe for automatic hand-off")
