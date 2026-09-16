from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
import time

from .action_plan import Action, ActionPlan


@dataclass(frozen=True)
class ConfirmationRecord:
    """Approval binding for one exact executable plan and time window."""
    fingerprint: str
    goal: str
    action_count: int
    issued_at: float
    expires_at: float


class ConfirmationManager:
    """Create and validate short-lived, single-use approvals for exact plans."""

    def __init__(self, ttl_seconds: float = 300.0) -> None:
        self.ttl_seconds = max(1.0, float(ttl_seconds))
        self._consumed: set[str] = set()

    def fingerprint_action(self, action: Action) -> str:
        payload = {
            "action": action.action,
            "target": action.target,
            "focus": action.focus,
            "parameters": action.parameters,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def fingerprint_plan(self, plan: ActionPlan) -> str:
        payload: dict[str, Any] = {
            "goal": plan.goal,
            "actions": [
                {
                    "action": action.action,
                    "target": action.target,
                    "focus": action.focus,
                    "parameters": action.parameters,
                }
                for action in plan.actions
            ],
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def issue(self, plan: ActionPlan) -> ConfirmationRecord:
        issued_at = time.time()
        return ConfirmationRecord(
            fingerprint=self.fingerprint_plan(plan),
            goal=plan.goal,
            action_count=len(plan.actions),
            issued_at=issued_at,
            expires_at=issued_at + self.ttl_seconds,
        )

    def validate(
        self,
        plan: ActionPlan,
        fingerprint: str | None,
        *,
        issued_at: float | None = None,
        expires_at: float | None = None,
    ) -> bool:
        if not fingerprint or fingerprint in self._consumed:
            return False
        if self.fingerprint_plan(plan) != fingerprint:
            return False
        if expires_at is not None and time.time() > expires_at:
            return False
        if issued_at is not None and issued_at > time.time() + 1.0:
            return False
        return True

    def consume(self, fingerprint: str | None) -> bool:
        """Consume an approval so the same confirmation cannot authorize twice."""
        if not fingerprint or fingerprint in self._consumed:
            return False
        self._consumed.add(fingerprint)
        return True
