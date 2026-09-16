from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from advi.providers import LLMProvider
from advi.core.structured_output import parse_structured_output

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReasoningDecision:
    """A turn-level decision used to route work without a rigid intent taxonomy."""

    mode: str = "conversation"
    goal: str = ""
    action: str | None = None
    confidence: float = 0.0
    missing_information: list[str] = field(default_factory=list)
    task_update: str | None = None
    memory_query: str | None = None
    memory_fact: str | None = None
    reason: str = ""
    fallback_reason: str | None = None
    intent_hint: str | None = None
    references: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "confidence", max(0.0, min(1.0, float(self.confidence))))


class ReasoningEngine:
    """Turn-level reasoning and routing.

    The model chooses a broad execution mode and, when useful, a concrete action.
    Python remains authoritative for capability availability, permissions, and execution.
    """

    MODES = {
        "conversation",
        "task_confirm",
        "task_cancel",
        "task_modify",
        "task_resume",
        "memory_query",
        "memory_update",
        "memory_forget",
        "action",
        "fallback",
        "ask_user",
        "research_followup",
    }

    def __init__(self, provider: LLMProvider, fallback_available: Callable[[], bool] | None = None) -> None:
        self.provider = provider
        self._fallback_available = fallback_available or (lambda: False)

    def decide(self, message: str, context: Any) -> ReasoningDecision:
        prompt = self._build_prompt(message, context)
        try:
            raw = self.provider.structured(
                [{"role": "user", "content": prompt}],
                self.DECISION_SCHEMA,
            )
            parsed = parse_structured_output(raw.text if hasattr(raw, "text") else str(raw), self.DECISION_SCHEMA)
            return self._normalize(parsed.data, message)
        except Exception as exc:
            logger.warning("Reasoning decision failed: %s", exc)
            return self._heuristic(message, context)

    def _build_prompt(self, message: str, context: Any) -> str:
        active = getattr(context, "active_task", None) or {}
        capabilities = getattr(context, "available_capabilities", "")
        recent = getattr(context, "recent_history", [])[-4:]
        history = "\n".join(f"{m.get('role', 'user').upper()}: {m.get('content', '')}" for m in recent)
        research = getattr(context, "recent_research", [])[-3:]
        return f"""You are ADVI's turn-level reasoning and routing component.

Choose what this turn needs, without forcing it into a fixed intent taxonomy.
The available modes are: conversation, task_confirm, task_cancel, task_modify,
task_resume, memory_query, memory_update, memory_forget, action, fallback, ask_user.

ACTIVE TASK:
{json.dumps(active, ensure_ascii=False)}

RECENT CONVERSATION:
{history or 'None'}

RECENT RESEARCH EVIDENCE:
{json.dumps(research, ensure_ascii=False) if research else "None"}

AVAILABLE CAPABILITIES:
{capabilities or 'None'}

USER MESSAGE:
{message!r}

Rules:
- Use action when ADVI's registered capabilities can perform the request.
- Use fallback only when the request needs desktop/browser agentic execution that the primary
  capability layer cannot reliably handle, or when the primary route has explicitly failed.
- Do not use fallback merely because wording is unfamiliar.
- Use ask_user when a required value genuinely cannot be inferred.
- Use research_followup when the user asks which source said something, asks for citations/source details, or asks about a conflict in research already collected.
- If an active task exists, recognize confirmations, cancellations, modifications, and resumes.
- Never claim an action is available just because you know its name; capabilities above are authoritative.
- A concrete action is optional. The goal should preserve the user's actual objective.
- intent_hint is OPTIONAL compatibility metadata for legacy feature paths only; do not use it to choose the routing mode.
- Prefer the simplest correct route, but do not sacrifice reliability merely to reduce calls.

Return ONLY JSON matching the schema."""

    DECISION_SCHEMA: dict[str, Any] = {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": sorted(MODES)},
            "goal": {"type": "string"},
            "action": {"type": ["string", "null"]},
            "confidence": {"type": "number"},
            "missing_information": {"type": "array", "items": {"type": "string"}},
            "task_update": {"type": ["string", "null"]},
            "memory_query": {"type": ["string", "null"]},
            "memory_fact": {"type": ["string", "null"]},
            "reason": {"type": "string"},
            "fallback_reason": {"type": ["string", "null"]},
            "intent_hint": {"type": ["string", "null"]},
            "references": {"type": "object"},
        },
        "required": ["mode", "goal", "confidence", "missing_information", "reason"],
    }

    def _normalize(self, data: dict[str, Any], message: str) -> ReasoningDecision:
        mode = str(data.get("mode", "conversation")).strip().lower()
        if mode not in self.MODES:
            # Unknown model output is not an application-level UNKNOWN state.
            mode = "fallback" if self._fallback_available() else "conversation"
        return ReasoningDecision(
            mode=mode,
            goal=str(data.get("goal") or message),
            action=data.get("action"),
            confidence=data.get("confidence", 0.0),
            missing_information=list(data.get("missing_information") or []),
            task_update=data.get("task_update"),
            memory_query=data.get("memory_query"),
            memory_fact=data.get("memory_fact"),
            reason=str(data.get("reason") or ""),
            fallback_reason=data.get("fallback_reason"),
            intent_hint=data.get("intent_hint"),
            references=dict(data.get("references") or {}),
        )

    def _heuristic(self, message: str, context: Any) -> ReasoningDecision:
        lower = message.lower().strip()
        active = getattr(context, "active_task", None)
        if active:
            status = str(active.get("status", ""))
            if status.endswith("awaiting_confirmation") or status == "awaiting_confirmation":
                if lower in {"yes", "y", "yeah", "sure", "ok", "proceed", "do it", "send it", "confirm"}:
                    return ReasoningDecision(mode="task_confirm", goal=message, confidence=1.0, reason="confirmation phrase")
                if lower in {"no", "n", "cancel", "stop", "abort", "nevermind", "never mind", "don't"}:
                    return ReasoningDecision(mode="task_cancel", goal=message, confidence=1.0, reason="cancellation phrase")
            if any(x in lower for x in ("go back", "resume", "continue with", "continue that")):
                return ReasoningDecision(mode="task_resume", goal=message, confidence=0.95, reason="task resume phrase")
            if any(x in lower for x in ("make it", "change the", "add ", "remove ", "instead")):
                return ReasoningDecision(mode="task_modify", goal=message, task_update=message, confidence=0.75, reason="task modification phrase")

        if any(x in lower for x in ("which source", "what source", "where did you get", "cite that", "show the source", "sources disagree", "which sources")):
            return ReasoningDecision(mode="research_followup", goal=message, confidence=0.95, reason="research evidence follow-up", references={"research_query": message})

        if lower.startswith(("remember that", "please remember")):
            return ReasoningDecision(mode="memory_update", goal=message, memory_fact=message, confidence=1.0, reason="memory update phrase")
        if any(x in lower for x in ("what is my ", "tell me my ", "what's my ")):
            return ReasoningDecision(mode="memory_query", goal=message, memory_query=message, confidence=0.9, reason="memory query phrase")
        if lower.startswith(("forget that", "please forget")):
            return ReasoningDecision(mode="memory_forget", goal=message, memory_fact=message, confidence=1.0, reason="memory forget phrase")
        if any(x in lower for x in ("open ", "search ", "navigate ", "save ", "create ", "read ", "delete ", "send email", "draft email", "click ")):
            return ReasoningDecision(mode="action", goal=message, confidence=0.65, reason="action-like wording")
        return ReasoningDecision(mode="conversation", goal=message, confidence=0.55, reason="default conversational fallback")

    @staticmethod
    def _extract_json(raw: str) -> str:
        text = raw.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].strip()
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return text[start:end + 1]
        raise ValueError("No JSON object found in reasoning response")
