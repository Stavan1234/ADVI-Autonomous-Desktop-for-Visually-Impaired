from __future__ import annotations

from types import SimpleNamespace

from advi.core.intent import IntentType
from advi.core.intent_detector import IntentDetector


class FakeStructuredProvider:
    def __init__(self, payload: str):
        self.payload = payload
        self.calls = 0
        self.last_messages = None
        self.last_schema = None

    def structured(self, messages, schema):
        self.calls += 1
        self.last_messages = messages
        self.last_schema = schema

        return SimpleNamespace(
            text=self.payload,
        )


class FailingStructuredProvider:
    def __init__(self):
        self.calls = 0

    def structured(self, messages, schema):
        self.calls += 1
        raise RuntimeError(
            "structured provider failure"
        )


def test_structured_intent_preserves_email_entities():
    provider = FakeStructuredProvider(
        """
        {
            "intent": "email_draft_create",
            "confidence": 0.95,
            "target": null,
            "entities": {
                "recipient": "Joel",
                "subject": "Sick leave",
                "body": "I am ill."
            },
            "parameters": {}
        }
        """
    )

    detector = IntentDetector(provider)

    result = detector.detect(
        "Send Joel an email saying I am ill."
    )

    assert result.type == IntentType.EMAIL_DRAFT_CREATE
    assert result.confidence == 0.95
    assert result.target is None

    assert result.entities == {
        "recipient": "Joel",
        "subject": "Sick leave",
        "body": "I am ill.",
    }

    assert result.parameters == {}
    assert provider.calls == 1


def test_structured_intent_preserves_null_target():
    provider = FakeStructuredProvider(
        """
        {
            "intent": "information_request",
            "confidence": 0.98,
            "target": null,
            "entities": {},
            "parameters": {}
        }
        """
    )

    detector = IntentDetector(provider)

    result = detector.detect(
        "What is the capital of France?"
    )

    assert result.type == IntentType.INFORMATION_REQUEST
    assert result.target is None
    assert result.entities == {}
    assert result.parameters == {}


def test_structured_intent_uses_current_task_context():
    provider = FakeStructuredProvider(
        """
        {
            "intent": "task_confirmation",
            "confidence": 0.99,
            "target": null,
            "entities": {},
            "parameters": {}
        }
        """
    )

    detector = IntentDetector(provider)

    task = SimpleNamespace(
        task_id="task-123",
        status=SimpleNamespace(
            value="awaiting_confirmation"
        ),
        steps=[],
        current_step=0,
        confirmation=SimpleNamespace(
            action="email_send",
            summary="Send email to Joel.",
        ),
    )

    detector.set_current_task(task)

    result = detector.detect(
        "Yes, send it."
    )

    assert result.type == IntentType.TASK_CONFIRMATION
    assert provider.calls == 1

    combined_prompt = "\n".join(
        message["content"]
        for message in provider.last_messages
    )

    assert "task-123" in combined_prompt
    assert "awaiting_confirmation" in combined_prompt
    assert "email_send" in combined_prompt


def test_structured_provider_failure_returns_unknown():
    provider = FailingStructuredProvider()

    detector = IntentDetector(provider)

    result = detector.detect(
        "What can you do?"
    )

    assert result.type == IntentType.UNKNOWN
    assert result.confidence == 0.0
    assert provider.calls == 1

def test_intent_schema_requires_explicit_entity_slots():
    schema = IntentDetector.INTENT_SCHEMA

    entities = schema["properties"]["entities"]

    assert entities["type"] == "object"

    required = set(
        entities["required"]
    )

    assert {
        "recipient",
        "subject",
        "body",
        "style",
        "message_id",
        "draft_id",
        "field",
        "value",
        "relationship",
        "property",
    }.issubset(required)

    assert (
        entities["properties"]["recipient"]["type"]
        == ["string", "null"]
    )

    assert (
        entities["properties"]["body"]["type"]
        == ["string", "null"]
    )    