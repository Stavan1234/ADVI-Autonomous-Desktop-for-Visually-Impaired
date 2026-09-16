from advi.brain.reasoning import ReasoningDecision
from advi.core.intent import IntentType
from advi.core.intent_bridge import intent_from_reasoning


def test_reasoning_action_maps_to_legacy_system_control():
    intent = intent_from_reasoning(
        ReasoningDecision(mode="action", goal="open notepad", confidence=0.9),
        "open notepad",
    )
    assert intent.type == IntentType.SYSTEM_CONTROL
    assert intent.confidence == 0.9


def test_specialized_email_hint_preserves_legacy_flow_without_routing_on_it():
    intent = intent_from_reasoning(
        ReasoningDecision(
            mode="action",
            goal="draft an email",
            confidence=0.95,
            intent_hint="email_draft_create",
            references={"entities": {"recipient": "Joel"}},
        ),
        "write Joel an email",
    )
    assert intent.type == IntentType.EMAIL_DRAFT_CREATE
    assert intent.entities["recipient"] == "Joel"


def test_unknown_reasoning_mode_never_creates_legacy_unknown_intent():
    intent = intent_from_reasoning(
        ReasoningDecision(mode="not-a-real-mode", goal="hello", confidence=0.1),
        "hello",
    )
    assert intent.type == IntentType.CONVERSATION
    assert intent.type != IntentType.UNKNOWN
