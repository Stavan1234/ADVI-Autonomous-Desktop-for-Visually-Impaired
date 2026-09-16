from __future__ import annotations

from dataclasses import dataclass, field as dc_field
import re
from typing import Any


@dataclass(frozen=True)
class FollowUpDecision:
    """Deterministic interpretation of a conversational follow-up."""

    kind: str = "none"  # none, modify, resume, reference_action
    task_update: str | None = None
    field: str | None = None
    value: str | None = None
    action: str | None = None
    confidence: float = 0.0
    references: tuple[dict[str, Any], ...] = dc_field(default_factory=tuple)


class FollowUpSemantics:
    """Resolve common task follow-ups without asking the LLM to infer state changes."""

    _FIELD_PATTERNS = (
        ("recipient", r"(?:change|set|update)\s+(?:the\s+)?(?:recipient|receiver|to)\s+(?:to\s+)?(.+)$"),
        ("subject", r"(?:change|set|update)\s+(?:the\s+)?subject\s+(?:to\s+)?(.+)$"),
        ("tone", r"(?:change|set|make)\s+(?:the\s+)?tone\s+(?:to\s+)?(.+)$"),
    )

    def interpret(self, message: str, context: Any) -> FollowUpDecision:
        text = message.strip()
        lower = text.lower()
        refs = tuple(getattr(context, "resolved_references", []) or [])
        has_task = bool(getattr(context, "active_task", None))
        if not text:
            return FollowUpDecision()

        if has_task and any(p in lower for p in ("continue with it", "continue with that", "resume", "go back to", "keep going with")):
            return FollowUpDecision(kind="resume", confidence=0.97, references=refs)

        if has_task:
            for field_name, pattern in self._FIELD_PATTERNS:
                match = re.match(pattern, text, flags=re.I)
                if match:
                    value = self._clean_value(match.group(1))
                    return FollowUpDecision(
                        kind="modify", task_update=text, field=field_name, value=value,
                        confidence=0.96, references=refs,
                    )

            patterns = (
                r"^make\s+it\s+(shorter|longer|more\s+formal|less\s+formal|concise|professional)\.?$",
                r"^(?:add|remove)\s+.+",
                r"^change\s+(?:the\s+)?(?:tone|wording|format)\b.+",
                r"^make\s+the\s+(?:subject|body|message)\b.+",
            )
            if any(re.match(p, text, flags=re.I) for p in patterns):
                return FollowUpDecision(kind="modify", task_update=text, confidence=0.9, references=refs)

        action_match = re.match(r"^(send|open|read|delete|edit|update)\s+(?:that|this|the\s+(?:previous|last)\s+(?:one|item|result|file))\.?$", text, re.I)
        if action_match and refs:
            action_map = {"send": "email_send", "open": "open_reference", "read": "read_reference", "delete": "delete_reference", "edit": "edit_reference", "update": "edit_reference"}
            return FollowUpDecision(
                kind="reference_action", action=action_map[action_match.group(1).lower()],
                confidence=0.9, references=refs,
            )

        return FollowUpDecision()

    @staticmethod
    def _clean_value(value: str) -> str:
        return value.strip().strip('"\'').rstrip(".")
