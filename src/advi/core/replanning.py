from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from .action_plan import Action, ActionPlan, ExecutionResult
from advi.core.structured_output import parse_structured_output

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReplanDecision:
    decision: str
    reason: str = ""
    action: Action | None = None
    await_user: bool = False


class ReplanningEngine:
    """Bounded, model-assisted recovery after an execution failure.

    The engine can propose a replacement *next action*, but Python remains
    authoritative: callers must validate the proposed action against the
    capability registry and confirmation policy before execution.
    """

    DECISION_SCHEMA = {
        "type": "object",
        "properties": {
            "decision": {"type": "string", "enum": ["replan", "done", "await_user"]},
            "reason": {"type": "string"},
            "action": {
                "type": ["object", "null"],
                "properties": {
                    "action": {"type": "string"},
                    "target": {"type": ["string", "null"]},
                    "focus": {"type": ["string", "null"]},
                    "parameters": {"type": "object"},
                },
            },
        },
        "required": ["decision", "reason", "action"],
    }

    def __init__(self, provider: Any, max_replans: int = 2) -> None:
        self.provider = provider
        self.max_replans = max(0, int(max_replans))

    def decide(
        self,
        goal: str,
        plan: ActionPlan,
        results: list[ExecutionResult],
        failed_action: Action,
        available_actions: list[str],
        replan_count: int,
        *,
        trigger: str = "execution_failure",
        goal_verification: dict[str, Any] | None = None,
    ) -> ReplanDecision:
        if replan_count >= self.max_replans:
            return ReplanDecision("done", "Replan limit reached.")

        failure = results[-1] if results else ExecutionResult(action=failed_action.action, success=False, error="unknown failure")
        prompt = self._build_prompt(
            goal, plan, results, failed_action, failure, available_actions, replan_count,
            trigger=trigger, goal_verification=goal_verification,
        )

        try:
            response = self.provider.structured(
                [{"role": "user", "content": prompt}],
                self.DECISION_SCHEMA,
            )
            data = parse_structured_output(response.text if hasattr(response, "text") else str(response), self.DECISION_SCHEMA).data
            return self._parse(data)
        except Exception as exc:
            logger.warning("Replanning decision failed: %s", exc)
            return ReplanDecision("done", f"Replanning unavailable: {exc}")

    def _build_prompt(
        self,
        goal: str,
        plan: ActionPlan,
        results: list[ExecutionResult],
        failed_action: Action,
        failure: ExecutionResult,
        available_actions: list[str],
        replan_count: int,
        *,
        trigger: str,
        goal_verification: dict[str, Any] | None,
    ) -> str:
        result_view = [
            {
                "action": r.action,
                "success": r.success,
                "verified": r.verified,
                "error": r.error,
                "data": r.data,
            }
            for r in results[-8:]
        ]
        return f"""You are ADVI's bounded recovery planner.

The original user goal is: {goal}

A planned action has failed. Decide what should happen NEXT.
You may propose exactly one replacement action, finish, or ask the user.

AUTHORITATIVE FAILURE:
{json.dumps({"action": failed_action.action, "parameters": failed_action.parameters, "error": failure.error, "verified": failure.verified}, ensure_ascii=False, default=str)}

EXECUTION HISTORY:
{json.dumps(result_view, ensure_ascii=False, default=str)}

CURRENT PLAN:
{json.dumps([a.model_dump() for a in plan.actions], ensure_ascii=False, default=str)}

AVAILABLE ACTIONS:
{json.dumps(sorted(set(available_actions)), ensure_ascii=False)}

REPLAN ATTEMPT: {replan_count + 1} of {self.max_replans}

RECOVERY TRIGGER: {trigger}
GOAL VERIFICATION:
{json.dumps(goal_verification or {}, ensure_ascii=False, default=str)}

RULES:
1. Trust execution results and observed state as authoritative.
2. When the trigger is verification_uncertain, prefer an action that can establish or repair the requested final state.
3. When the trigger is execution_failure or verification_failed, prefer an alternative route that can accomplish the same goal.
4. Do not repeat the failed action unless the failure clearly indicates a transient issue and a retry is not otherwise handled.
4. Never invent recipients, file paths, IDs, URLs, or values.
5. Never bypass confirmation or permission requirements.
6. Return exactly one next action when choosing 'replan'.
7. Choose 'await_user' when the user must provide missing information or make a decision.
8. Choose 'done' when no safe recovery is available.

Return JSON only."""

    @staticmethod
    def _parse(data: dict[str, Any]) -> ReplanDecision:
        decision = str(data.get("decision", "done")).strip().lower()
        if decision not in {"replan", "done", "await_user"}:
            decision = "done"
        reason = str(data.get("reason") or "").strip()
        if decision != "replan":
            return ReplanDecision(decision, reason, await_user=decision == "await_user")

        raw = data.get("action")
        if not isinstance(raw, dict):
            return ReplanDecision("done", "Replanner requested a replan without an action.")

        action = str(raw.get("action") or "").strip()
        if not action:
            return ReplanDecision("done", "Replanner returned an empty action.")
        params = raw.get("parameters")
        if not isinstance(params, dict):
            params = {}
        return ReplanDecision(
            "replan",
            reason,
            action=Action(
                action=action,
                target=raw.get("target"),
                focus=raw.get("focus"),
                parameters=params,
            ),
        )

    @staticmethod
    def _extract_json(raw: str) -> str:
        text = raw.strip()
        if text.startswith("```"):
            text = text.removeprefix("```json").removeprefix("```").strip()
        if text.endswith("```"):
            text = text.removesuffix("```").strip()
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("No JSON object found")
        return text[start:end + 1]
