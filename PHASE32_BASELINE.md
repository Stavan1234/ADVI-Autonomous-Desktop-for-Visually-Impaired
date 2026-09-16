# Phase 32 Baseline — Multi-Source Browser Research

## Objective
Expand browser research from one selected result to a bounded multi-source evidence workflow with controlled pagination and source diversity.

## Implementation
- Added `research_web_multi` as a first-class browser capability action.
- Added deterministic candidate collection across at most two Google result pages.
- Added a hard maximum of five sources per run and de-duplication by URL/domain.
- Added bounded page-content extraction per source.
- Aggregates readable evidence with per-source URL, title, domain, readability, content length, and navigation status.
- Added canonical action contract and registry semantics for `research_web_multi`.
- No LLM-generated selectors, autonomous crawling, authentication automation, or unbounded pagination.

## Safety / Reliability
- Empty queries fail deterministically.
- Missing browser tabs fail deterministically.
- Source collection is bounded by source count and pagination limits.
- Same-domain duplicates are excluded to improve source diversity.
- Partial source failures are preserved as evidence; the workflow only fails completely when no source yields readable content.
- Existing capability policy, execution, observation, verification, and fallback boundaries remain in force.

## Tests
- Phase 32 multi-source browser tests: 5 passed.
- Non-blocked repository suite: 164 passed (excluding the existing root X11-dependent fallback tests and the direct Groq import blocker in `tests/test_foundation.py`).
- `python -m compileall -q src/advi`: passed.

## Deliberate Non-Changes
- No general workflow engine.
- No autonomous unbounded crawler.
- No LLM-driven DOM selector execution.
- No automatic source synthesis claim; returned data is evidence for the brain/summarizer.
- No changes to David fallback semantics.

## Next Direction
The next phase should use the aggregated browser evidence in the cognitive layer so ADVI can produce grounded multi-source answers while retaining source traceability and uncertainty.
