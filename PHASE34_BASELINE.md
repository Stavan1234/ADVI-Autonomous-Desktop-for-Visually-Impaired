# Phase 34 Baseline — Research Evidence Persistence & Conflict Handling

## Objective
Persist bounded research evidence beyond the active task/session and support source-traceable follow-up questions and explicit conflict reporting.

## Implemented
- Added `src/advi/core/research_evidence.py`.
- Added `ResearchEvidenceStore` backed by the existing SQLite database when task persistence is configured.
- Stores research question, bounded source metadata/content, synthesized answer, source-claim mappings, uncertainty, and detected conflicts.
- Added `StoredResearch` and `ResearchConflict` models.
- Added bounded `latest()` and question lookup support.
- Added deterministic, conservative conflict detection for explicit polarity/value/topic disagreement; no LLM is used to invent conflicts.
- `ResearchSynthesizer` accepts the evidence store for shared persistence wiring.
- `ADVIAgent` persists successful `research_web_multi` results after synthesis.
- Recent research evidence is surfaced to reasoning context.
- Added `research_followup` routing for source/citation/conflict follow-up requests.
- Added deterministic responses that trace claims to the exact stored source title and URL.

## Safety / Reliability
- Stored content is bounded per source.
- Follow-up source references are derived only from stored source records.
- No source ID/URL is invented.
- Research conflicts are reported as recorded disagreements, not resolved by unsupported inference.
- Failure to initialize/retrieve the evidence store does not crash the main agent.

## Validation
- `python -m compileall -q src/advi` passes.
- Phase 34 targeted tests: 5/5 pass.
- Full `tests/` suite excluding the pre-existing direct Groq dependency blocker `tests/test_foundation.py`: all tests pass.

## Deliberate Non-Changes
- No general-purpose vector database added.
- No unrestricted web crawler added.
- No automatic resolution of conflicting sources.
- No replacement of existing long-term personal memory with research evidence.
