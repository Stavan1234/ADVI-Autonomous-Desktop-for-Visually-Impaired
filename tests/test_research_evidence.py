from pathlib import Path

from advi.core.research_evidence import ResearchEvidenceStore


def test_store_round_trip(tmp_path: Path):
    store = ResearchEvidenceStore(tmp_path / "advi.db")
    saved = store.save(
        "r1", "How does ADVI work?",
        {"sources": [
            {"readable": True, "title": "One", "url": "https://one.example", "domain": "one.example", "content": "ADVI uses a registry."},
            {"readable": True, "title": "Two", "url": "https://two.example", "domain": "two.example", "content": "ADVI uses bounded research."},
        ]},
        answer="It uses a registry [S1].",
        source_claims=[{"source_index": 1, "claim": "ADVI uses a registry."}],
    )
    loaded = store.get("r1")
    assert loaded and loaded.answer == saved.answer
    assert loaded.sources[0]["url"] == "https://one.example"
    assert loaded.source_claims[0]["source_index"] == 1


def test_latest_is_bounded(tmp_path: Path):
    store = ResearchEvidenceStore(tmp_path / "advi.db")
    for i in range(5):
        store.save(str(i), f"Question {i}", {"sources": []})
    assert [x.research_id for x in store.latest(2)] == ["4", "3"]


def test_detects_explicit_polarity_conflict(tmp_path: Path):
    sources = [
        {"index": 1, "content": "ADVI is available offline."},
        {"index": 2, "content": "ADVI is not available offline."},
    ]
    conflicts = ResearchEvidenceStore.detect_conflicts(sources)
    assert conflicts
    assert conflicts[0].source_indices == (1, 2)


def test_research_followup_heuristic_routes_to_sources(tmp_path: Path):
    from advi.brain.reasoning import ReasoningEngine

    class FailingProvider:
        def structured(self, *args, **kwargs):
            raise RuntimeError("down")

    decision = ReasoningEngine(FailingProvider()).decide("which source said that?", type("C", (), {})())
    assert decision.mode == "research_followup"


def test_agent_exposes_stored_research_followup(tmp_path: Path):
    from advi.brain.agent import ADVIAgent

    class Provider:
        name = "test"
        model = "test"
        def structured(self, *args, **kwargs):
            raise RuntimeError("down")

    store = ResearchEvidenceStore(tmp_path / "advi.db")
    store.save(
        "r1", "How does ADVI work?",
        {"sources": [
            {"readable": True, "title": "ADVI Docs", "url": "https://docs.example/advi", "domain": "docs.example", "content": "ADVI uses a registry."},
        ]},
        answer="ADVI uses a registry [S1].",
        source_claims=[{"source_index": 1, "claim": "ADVI uses a registry."}],
    )
    agent = ADVIAgent(Provider(), research_evidence_store=store)
    response = agent._answer_research_followup("which source said that?", "which source said that?")
    assert "[S1]" in response.text
    assert "docs.example" in response.text
