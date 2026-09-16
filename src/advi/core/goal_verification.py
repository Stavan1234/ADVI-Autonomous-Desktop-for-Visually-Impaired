from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .action_plan import ActionPlan, ExecutionResult, VerificationStatus


class GoalVerificationStatus(str):
    VERIFIED = "verified"
    FAILED = "failed"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class GoalVerification:
    status: str
    goal: str
    evidence: list[dict[str, Any]] = field(default_factory=list)
    reason: str = ""

    @property
    def verified(self) -> bool:
        return self.status == GoalVerificationStatus.VERIFIED


class GoalVerifier:
    """Determine whether the requested goal is supported by action + state evidence.

    This is intentionally conservative. It never upgrades an uncertain action into a
    verified goal without concrete post-action evidence.
    """

    def verify(self, plan: ActionPlan, results: list[ExecutionResult]) -> GoalVerification:
        meaningful = [r for r in results if r.action != "finish"]
        if not meaningful:
            return GoalVerification(
                GoalVerificationStatus.UNCERTAIN,
                plan.goal,
                reason="No meaningful executable result was produced.",
            )

        failed = [r for r in meaningful if not r.success or r.verification_status == VerificationStatus.FAILED]
        if failed:
            first = failed[0]
            return GoalVerification(
                GoalVerificationStatus.FAILED,
                plan.goal,
                evidence=[self._evidence(r) for r in meaningful],
                reason=first.error or f"Action '{first.action}' failed.",
            )

        uncertain = [
            r for r in meaningful
            if not r.verified and r.verification_status == VerificationStatus.UNCERTAIN
        ]
        if uncertain:
            return GoalVerification(
                GoalVerificationStatus.UNCERTAIN,
                plan.goal,
                evidence=[self._evidence(r) for r in meaningful],
                reason=f"{len(uncertain)} action result(s) lack definitive post-state evidence.",
            )

        return GoalVerification(
            GoalVerificationStatus.VERIFIED,
            plan.goal,
            evidence=[self._evidence(r) for r in meaningful],
            reason="All meaningful actions have definitive verification evidence.",
        )

    @staticmethod
    def _evidence(result: ExecutionResult) -> dict[str, Any]:
        metadata = result.metadata or {}
        return {
            "action": result.action,
            "success": result.success,
            "verification_status": result.verification_status.value,
            "verification_details": result.verification_details,
            "state_before": metadata.get("state_before"),
            "state_after": metadata.get("state_after"),
        }


__all__ = ["GoalVerificationStatus", "GoalVerification", "GoalVerifier"]
