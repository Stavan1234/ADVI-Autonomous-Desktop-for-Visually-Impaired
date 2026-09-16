from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from advi.capabilities.registry import CapabilityRegistry
from advi.core.action_plan import Action, ActionPlan
from advi.core.action_contracts import validate_and_normalize_action
from advi.providers import LLMProvider
from advi.core.structured_output import parse_structured_output

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlanningHints:
    """Structured hints produced upstream by ReasoningEngine."""

    preferred_action: str | None = None
    reason: str = ""
    references: dict[str, Any] = field(default_factory=dict)


class PlannerEngine:
    """Turn a resolved user goal into an executable ActionPlan.

    The planner is deliberately narrower than the reasoning layer: it decides *how*
    to accomplish an already-selected goal, using only actions exposed by the registry.
    """

    def __init__(self, provider: LLMProvider, registry: CapabilityRegistry) -> None:
        self.provider = provider
        self.registry = registry

    def plan(self, goal: str, context: Any, hints: PlanningHints | None = None) -> ActionPlan:
        hints = hints or PlanningHints()
        actions_list = self.registry.actions_for_prompt()
        prompt = self._build_prompt(goal, context, actions_list, hints)

        try:
            raw = self.provider.structured(
                [{"role": "user", "content": prompt}],
                self.PLAN_SCHEMA,
            )
            text = raw.text if hasattr(raw, "text") else str(raw)
            data = parse_structured_output(text, self.PLAN_SCHEMA).data
            return self._normalize(data, goal)
        except Exception as exc:
            logger.exception("Action planning failed: %s", exc)
            return ActionPlan(goal=goal, actions=[])

    def _actions_prompt(self) -> str:
        return self.registry.actions_for_prompt()

    def _build_prompt(
        self,
        goal: str,
        context: Any,
        actions_list: str,
        hints: PlanningHints,
    ) -> str:
        formatted = context.format_prompt_context() if hasattr(context, "format_prompt_context") else str(context)
        return f"""You are ADVI's Action Planner, a subsystem for turning a resolved user goal into a small executable plan.

CONTEXT:
{formatted}

USER GOAL:
{goal!r}

UPSTREAM REASONING HINTS:
- preferred_action: {hints.preferred_action or 'none'}
- reason: {hints.reason or 'none'}
- references: {json.dumps(hints.references, ensure_ascii=False)}

AVAILABLE ACTIONS (authoritative; use ONLY these exact names):
{actions_list}

Planning rules:
- Preserve the user's actual objective; do not invent a different goal.
- Prefer the fewest reliable actions needed to achieve the objective.
- Use the preferred_action when it is compatible with the goal and available.
- Use only available actions above. Never invent action names.
- Put all required concrete values in parameters or mark them as missing_information.
- Mark confirmation_required for irreversible actions such as email_send, delete_file, or submit.
- Use semantic target/focus fields when they improve desktop/browser execution.
- Do not add a finish action unless the registry actually exposes 'finish'.
- A plan may be empty only when the goal cannot be materialized with current capabilities.

Return ONLY JSON matching the schema."""

    PLAN_SCHEMA: dict[str, Any] = {
        "type": "object",
        "properties": {
            "goal": {"type": "string"},
            "reason": {"type": "string"},
            "missing_information": {"type": "array", "items": {"type": "string"}},
            "confirmation_required": {"type": "boolean"},
            "confirmation_prompt": {"type": "string"},
            "actions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string"},
                        "parameters": {"type": "object"},
                        "focus": {"type": ["string", "null"]},
                        "target": {"type": ["string", "null"]},
                        "reason": {"type": ["string", "null"]},
                    },
                    "required": ["action", "parameters"],
                },
            },
        },
        "required": ["goal", "missing_information", "confirmation_required", "actions"],
    }

    def _normalize(self, data: dict[str, Any], goal: str) -> ActionPlan:
        actions: list[Action] = []
        invalid: list[str] = []
        for item in data.get("actions", []) or []:
            name = str(item.get("action", "")).strip()
            if not name:
                continue
            if not self.registry.is_action_supported(name):
                invalid.append(name)
                continue
            candidate = Action(
                action=name,
                parameters=dict(item.get("parameters") or {}),
                focus=item.get("focus"),
                target=item.get("target"),
                reason=item.get("reason"),
            )
            normalized, errors = validate_and_normalize_action(candidate)
            if errors:
                invalid.append(f"{name}: {'; '.join(errors)}")
                continue
            if normalized is not None:
                actions.append(normalized)

        missing = list(data.get("missing_information") or [])
        reason = str(data.get("reason") or "")
        if invalid:
            reason = (reason + " " if reason else "") + f"Ignored unavailable actions: {', '.join(invalid)}."

        return ActionPlan(
            goal=str(data.get("goal") or goal),
            actions=actions,
            reason=reason,
            missing_information=missing,
            confirmation_required=bool(data.get("confirmation_required", False)),
            confirmation_prompt=str(data.get("confirmation_prompt") or ""),
        )

    @staticmethod
    def _extract_json(raw: str) -> str:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return text[start : end + 1]
        raise ValueError("No JSON object found in planning response")
