from __future__ import annotations

import json

from advi.brain.reasoning import ReasoningDecision, ReasoningEngine
from advi.providers import LLMResponse


class FakeProvider:
    name = "fake"
    model = "fake-model"

    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def chat(self, messages):
        self.calls.append(("chat", messages))
        return LLMResponse(text=json.dumps(self.payload), provider=self.name, model=self.model)

    def structured(self, messages, schema):
        self.calls.append(("structured", messages, schema))
        return LLMResponse(text=json.dumps(self.payload), provider=self.name, model=self.model)


def test_reasoning_chooses_broad_action_mode_without_unknown():
    provider = FakeProvider({
        "mode": "action",
        "goal": "Open Notepad",
        "action": "open_application",
        "confidence": 0.94,
        "missing_information": [],
        "reason": "desktop capability is available",
    })
    decision = ReasoningEngine(provider).decide("please open notepad", type("C", (), {})())
    assert decision.mode == "action"
    assert decision.action == "open_application"
    assert decision.confidence == 0.94
    assert provider.calls[0][0] == "structured"


def test_invalid_model_mode_is_routed_without_unknown_state():
    provider = FakeProvider({
        "mode": "UNKNOWN",
        "goal": "do something unusual",
        "confidence": 0.1,
        "missing_information": [],
        "reason": "unrecognized mode",
    })
    decision = ReasoningEngine(provider).decide("do something unusual", type("C", (), {})())
    assert decision.mode == "conversation"
    assert decision.mode != "unknown"


def test_heuristic_handles_confirmation_before_llm_failure():
    class BrokenProvider(FakeProvider):
        def structured(self, messages, schema):
            raise RuntimeError("offline")

    context = type("C", (), {"active_task": {"status": "awaiting_confirmation"}})()
    decision = ReasoningEngine(BrokenProvider({})).decide("yes", context)
    assert decision == ReasoningDecision(
        mode="task_confirm",
        goal="yes",
        confidence=1.0,
        reason="confirmation phrase",
    )
