from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from advi.capabilities.registry import CapabilityRegistry
from .action_plan import Action


class PolicyDisposition(str, Enum):
    ALLOW = "allow"
    CONFIRM = "confirm"
    DENY = "deny"


@dataclass(frozen=True)
class PolicyDecision:
    action: str
    disposition: PolicyDisposition
    reason: str


class CapabilityPolicy:
    """Single authoritative policy gate for side effects and confirmation.

    Planning may request confirmation, but it cannot lower a system-required gate.
    The policy also rejects unavailable actions and critical actions without a
    capability that explicitly supports them.
    """

    def __init__(
        self,
        registry: CapabilityRegistry,
        *,
        deny_critical_without_confirmation: bool = True,
    ) -> None:
        self.registry = registry
        self.deny_critical_without_confirmation = deny_critical_without_confirmation

    def evaluate_action(self, action: Action) -> PolicyDecision:
        spec = self.registry.get_action_spec(action.action)
        if spec is None:
            return PolicyDecision(action.action, PolicyDisposition.DENY, "action_unavailable")

        if spec.requires_confirmation:
            return PolicyDecision(action.action, PolicyDisposition.CONFIRM, "confirmation_required_by_capability_policy")

        if (
            self.deny_critical_without_confirmation
            and spec.side_effect.lower() == "critical"
        ):
            return PolicyDecision(action.action, PolicyDisposition.CONFIRM, "critical_side_effect_requires_confirmation")

        return PolicyDecision(action.action, PolicyDisposition.ALLOW, "allowed_by_capability_policy")

    def evaluate_plan(self, actions: Iterable[Action]) -> list[PolicyDecision]:
        return [self.evaluate_action(action) for action in actions]

    def confirmation_actions(self, actions: Iterable[Action]) -> list[Action]:
        return [
            action
            for action in actions
            if self.evaluate_action(action).disposition == PolicyDisposition.CONFIRM
        ]

    def first_denial(self, actions: Iterable[Action]) -> PolicyDecision | None:
        for decision in self.evaluate_plan(actions):
            if decision.disposition == PolicyDisposition.DENY:
                return decision
        return None
