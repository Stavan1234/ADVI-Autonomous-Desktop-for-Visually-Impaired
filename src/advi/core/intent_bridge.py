from __future__ import annotations

from typing import Any

from advi.brain.reasoning import ReasoningDecision
from .intent import Intent, IntentType


# Compatibility-only mapping. The brain routes on ReasoningDecision.mode; these
# legacy intent types exist only for older ConversationEngine/TaskCoordinator APIs.
LEGACY_HINTS = {item.value for item in IntentType}

_MODE_DEFAULTS: dict[str, IntentType] = {
    "conversation": IntentType.CONVERSATION,
    "memory_query": IntentType.MEMORY_RETRIEVAL,
    "memory_update": IntentType.MEMORY_UPDATE,
    "memory_forget": IntentType.MEMORY_FORGET,
    "action": IntentType.SYSTEM_CONTROL,
    "ask_user": IntentType.INFORMATION_REQUEST,
    "fallback": IntentType.SYSTEM_CONTROL,
    "task_confirm": IntentType.TASK_CONFIRMATION,
    "task_cancel": IntentType.TASK_CANCEL,
    "task_modify": IntentType.TASK_MODIFICATION,
    "task_resume": IntentType.TASK_RESUME,
}


def intent_from_reasoning(decision: ReasoningDecision, original_input: str) -> Intent:
    """Adapt the unified reasoning result to the legacy Intent API.

    This is deliberately one-way: legacy intent labels never drive the new brain.
    A specialized ``intent_hint`` can preserve old feature-specific flows such as
    email composition without restoring the old classifier as a routing authority.
    """
    hint = str(getattr(decision, "intent_hint", "") or "").strip().lower()
    try:
        intent_type = IntentType(hint) if hint in LEGACY_HINTS else _MODE_DEFAULTS.get(
            decision.mode, IntentType.CONVERSATION
        )
    except ValueError:
        intent_type = _MODE_DEFAULTS.get(decision.mode, IntentType.CONVERSATION)

    entities: dict[str, str] = {}
    parameters: dict[str, str] = {}
    references: dict[str, Any] = dict(decision.references or {})

    for source, destination in ((references.get("entities"), entities), (references.get("parameters"), parameters)):
        if isinstance(source, dict):
            destination.update({str(k): str(v) for k, v in source.items() if v is not None})

    target = references.get("target")
    if target is not None:
        target = str(target).strip() or None

    return Intent(
        type=intent_type,
        confidence=decision.confidence,
        original_input=original_input,
        target=target,
        entities=entities,
        parameters=parameters,
    )
