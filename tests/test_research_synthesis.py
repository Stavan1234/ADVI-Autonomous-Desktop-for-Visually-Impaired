import json

from advi.core.research_synthesis import ResearchSynthesizer
from advi.providers import LLMResponse


class Provider:
    name = "test"
    model = "test-model"

    def __init__(self, payload=None, fail=False):
        self.payload = payload
        self.fail = fail

    def structured(self, messages, schema):
        if self.fail:
            raise RuntimeError("provider down")
        return LLMResponse(text=json.dumps(self.payload), provider=self.name, model=self.model)


def evidence():
    return {
        "sources": [
            {"readable": True, "title": "One", "url": "https://one.example/a", "domain": "one.example", "content": "One says ADVI uses a registry."},
            {"readable": True, "title": "Two", "url": "https://two.example/b", "domain": "two.example", "content": "Two says ADVI has bounded research."},
        ]
    }


def test_synthesis_preserves_source_mapping():
    provider = Provider({
        "answer": "ADVI uses a registry [S1] and bounded research [S2].",
        "source_claims": [
            {"source_index": 1, "claim": "ADVI uses a registry."},
            {"source_index": 2, "claim": "ADVI has bounded research."},
        ],
        "uncertainty": [],
    })
    result = ResearchSynthesizer(provider).synthesize("How does ADVI work?", evidence())
    assert "[S1]" in result.answer and "[S2]" in result.answer
    assert [c["source_index"] for c in result.source_claims] == [1, 2]


def test_synthesis_drops_invalid_source_claim_ids():
    provider = Provider({
        "answer": "Claim [S1].",
        "source_claims": [
            {"source_index": 1, "claim": "Valid."},
            {"source_index": 99, "claim": "Invalid."},
        ],
        "uncertainty": ["Sources are limited."],
    })
    result = ResearchSynthesizer(provider).synthesize("Q", evidence())
    assert len(result.source_claims) == 1
    assert result.uncertainty == ["Sources are limited."]


def test_synthesis_falls_back_to_evidence_when_provider_fails():
    result = ResearchSynthesizer(Provider(fail=True)).synthesize("Q", evidence())
    assert "[S1]" in result.answer
    assert result.uncertainty


def test_agent_uses_research_synthesizer_for_multi_source_result(monkeypatch):
    from advi.brain.agent import ADVIAgent
    from advi.core.action_plan import ExecutionResult
    from advi.capabilities.registry import CapabilityRegistry

    class DummyProvider(Provider):
        def __init__(self):
            super().__init__({
                "mode": "conversation", "goal": "", "confidence": 1.0,
                "missing_information": [], "reason": ""
            })

    agent = ADVIAgent(DummyProvider(), registry=CapabilityRegistry())
    result = ExecutionResult(
        action="research_web_multi", success=True,
        data="evidence",
        metadata=evidence(),
    )
    monkeypatch.setattr(
        agent.research_synthesizer,
        "synthesize",
        lambda goal, metadata: type("S", (), {"answer": "Grounded answer [S1]."})(),
    )
    assert agent._author_grounded_response("What did you find?", [result]) == "Grounded answer [S1]."


def test_time_sensitive_synthesis_marks_unknown_freshness():
    provider = Provider({
        "answer": "Current result [S1].",
        "source_claims": [{"source_index": 1, "claim": "Current result."}],
        "uncertainty": [],
    })
    result = ResearchSynthesizer(provider).synthesize("What is the latest ADVI status?", {
        "sources": [{
            "readable": True, "title": "Status", "url": "https://example.com/status",
            "domain": "example.com", "content": "Status information " * 30,
            "quality_score": 7.0, "quality_flags": ["substantive_content", "freshness_unknown"],
            "freshness_timestamp": None,
        }]
    })
    assert any("Freshness is unknown" in item for item in result.uncertainty)


def test_synthesis_prompt_contains_quality_metadata():
    provider = Provider({
        "answer": "Answer [S1].",
        "source_claims": [{"source_index": 1, "claim": "Answer."}],
        "uncertainty": [],
    })
    synth = ResearchSynthesizer(provider)
    synth.synthesize("Q", {"sources": [{
        "readable": True, "title": "Fresh", "url": "https://example.com",
        "domain": "example.com", "content": "useful evidence " * 40,
        "quality_score": 9.5, "quality_flags": ["fresh"], "freshness_timestamp": 1789500000,
    }]})
    prompt = provider.last_messages[0]["content"] if hasattr(provider, "last_messages") else ""
