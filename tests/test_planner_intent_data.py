from advi.core.intent import Intent, IntentType
from advi.core.planner import Planner


def test_planner_preserves_email_entities():
    intent = Intent(
        type=IntentType.EMAIL_DRAFT_CREATE,
        confidence=0.95,
        original_input=(
            "Send Joel an email saying I am ill."
        ),
        entities={
            "recipient": "Joel",
            "subject": "Sick leave",
            "body": "I am ill.",
        },
        parameters={},
    )

    plan = Planner().create_plan(intent)

    assert plan.status.value == "ready"
    assert len(plan.steps) == 1

    step = plan.steps[0]

    assert step.action == "email_draft_create"

    assert step.parameters == {
        "recipient": "Joel",
        "subject": "Sick leave",
        "body": "I am ill.",
    }


def test_planner_accepts_email_values_from_parameters():
    intent = Intent(
        type=IntentType.EMAIL_DRAFT_CREATE,
        confidence=0.95,
        original_input=(
            "Send Joel an email saying I am ill."
        ),
        entities={},
        parameters={
            "recipient": "Joel",
            "subject": "Sick leave",
            "body": "I am ill.",
        },
    )

    plan = Planner().create_plan(intent)

    assert plan.steps[0].parameters == {
        "recipient": "Joel",
        "subject": "Sick leave",
        "body": "I am ill.",
    }