from types import SimpleNamespace

from advi.core.conversation import ConversationEngine
from advi.core.intent import Intent, IntentType


class FakeProvider:
    def __init__(self, response_text):
        self.response_text = response_text
        self.calls = 0

    def chat(self, messages):
        self.calls += 1

        class Result:
            pass

        result = Result()
        result.text = self.response_text
        return result


def test_email_composition_uses_groq_to_write_complete_email():
    provider = FakeProvider(
        """
        SUBJECT: Happy Birthday Joel
        BODY:
        Good morning Joel,

        Wishing you a very happy birthday! I hope you
        have a wonderful day filled with joy and happiness.

        Best regards,
        Stavan
        END_BODY
        """
    )

    engine = ConversationEngine(
        provider=provider,
    )

    intent = Intent(
        type=IntentType.EMAIL_DRAFT_CREATE,
        confidence=0.98,
        original_input=(
            "Write an email to Joel saying "
            "good morning happy birthday."
        ),
        entities={
            "recipient": "Joel",
            "body": "good morning happy birthday",
        },
        parameters={
            "recipient": "Joel",
            "body": "good morning happy birthday",
        },
    )

    result = engine._compose_email_draft(intent)

    assert result.entities["recipient"] == "Joel"
    assert result.entities["subject"] == "Happy Birthday Joel"
    assert "Good morning Joel" in result.entities["body"]
    assert "happy birthday" in result.entities["body"].lower()

    assert result.parameters["recipient"] == "Joel"
    assert result.parameters["subject"] == "Happy Birthday Joel"
    assert result.parameters["body"] == result.entities["body"]

    assert provider.calls == 1

def test_email_composition_preserves_explicit_recipient_and_uses_groq_body():
    provider = FakeProvider(
        """
        SUBJECT: Project Update
        BODY:
        Dear David,

        I wanted to let you know that the project is ready.
        Please let me know if you have any questions.

        Best regards,
        Stavan
        END_BODY
        """
    )

    engine = ConversationEngine(
        provider=provider,
    )

    intent = Intent(
        type=IntentType.EMAIL_DRAFT_CREATE,
        confidence=0.98,
        original_input=(
            "Send an email to David saying the project is ready."
        ),
        entities={
            "recipient": "david@example.com",
            "body": "the project is ready",
        },
        parameters={
            "recipient": "david@example.com",
            "body": "the project is ready",
        },
    )

    result = engine._compose_email_draft(intent)

    assert result.entities["recipient"] == "david@example.com"
    assert result.entities["subject"] == "Project Update"
    assert result.entities["body"].startswith("Dear David")

    assert result.parameters["recipient"] == "david@example.com"
    assert result.parameters["subject"] == "Project Update"
    assert result.parameters["body"] == result.entities["body"]

    assert provider.calls == 1