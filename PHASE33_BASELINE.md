# Phase 33 Baseline — Grounded Multi-Source Research Synthesis

## Objective
Connect bounded multi-source browser evidence to the cognitive response layer so research answers remain grounded, source-traceable, and explicit about uncertainty.

## Implementation
- Added `src/advi/core/research_synthesis.py`.
- Added `ResearchSource` and `ResearchSynthesis` structured models.
- Added `ResearchSynthesizer` that uses the existing LLM provider structured-output boundary.
- Synthesis prompts require inline source markers (`[S1]`, `[S2]`, etc.) for substantive factual claims.
- Source-claim mappings are validated against real collected source indexes; invented source IDs are dropped.
- Source disagreement and insufficient evidence are explicitly represented through `uncertainty`.
- Added deterministic evidence-only fallback when the synthesis provider fails; it never fabricates a conclusion.
- Wired `ADVIAgent` to synthesize successful `research_web_multi` results before producing the final user response.

## Safety / Reliability
- The synthesizer receives only the bounded source evidence returned by the browser capability.
- It is instructed not to use outside facts or invent citations.
- Invalid source mappings are discarded.
- Provider failure falls back to source excerpts rather than an unsupported summary.
- No arbitrary web browsing, autonomous crawling, or new execution path was introduced.

## Tests
- Phase 33 synthesis + integration tests: 17 passed.
- `python -m compileall -q src/advi`: passed.
- Broader regression coverage was exercised with the existing browser/end-to-end suites.

## Deliberate Non-Changes
- No claim-ranking or source-quality scoring was introduced.
- No external citation format or URL generation was added beyond preserving the collected source URLs/indexes.
- No change to David fallback semantics.
- No new workflow engine.

## Next Direction
Next phase should improve research evidence quality and answer grounding at the interface boundary: ensure multi-source evidence is preserved in task/session context, expose source references to responses, and test conflicting or incomplete sources end-to-end.
