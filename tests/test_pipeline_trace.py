from __future__ import annotations

import json
import logging

from advi.core.intent import Intent, IntentType
from advi.core.pipeline_trace import (
    begin_turn,
    intent_to_dict,
    safe_repr,
    trace,
)


def test_begin_turn_sets_correlation_id():
    turn_id = begin_turn("hello")
    assert turn_id
    assert "-" in turn_id


def test_safe_repr_redacts_api_keys():
    payload = {
        "api_key": "AIzaSyD123456789012345678901234567890",
        "message": "hello",
    }
    text = safe_repr(payload)
    assert "AIzaSy" not in text
    assert "<REDACTED>" in text


def test_trace_emits_structured_log(caplog):
    caplog.set_level(logging.INFO, logger="advi.trace")
    turn_id = begin_turn("Send email to Joel")

    trace(
        "test.stage",
        intent=intent_to_dict(
            Intent(
                type=IntentType.EMAIL_DRAFT_CREATE,
                confidence=0.9,
                original_input="Send email to Joel",
                entities={"recipient": "Joel"},
            )
        ),
        turn_id=turn_id,
    )

    assert any(
        "[TRACE]" in record.message
        and "test.stage" in record.message
        for record in caplog.records
    )


def test_intent_to_dict_includes_entities():
    intent = Intent(
        type=IntentType.EMAIL_DRAFT_CREATE,
        confidence=0.98,
        original_input="test",
        entities={"recipient": "Joel"},
        parameters={"subject": "Hi"},
    )
    data = intent_to_dict(intent)
    assert data["entities"]["recipient"] == "Joel"
    assert data["parameters"]["subject"] == "Hi"

    serialized = json.loads(safe_repr(data))
    assert serialized["type"] == "email_draft_create"
