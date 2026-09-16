# Phase 35 Baseline — Research Quality & Source Selection

## Objective
Improve bounded web research quality before synthesis by scoring evidence quality, using freshness when available, canonicalizing URLs, removing duplicate/near-duplicate content, and preserving source diversity.

## Implemented
- Added `src/advi/core/research_quality.py`.
- Added deterministic URL canonicalization that removes common tracking parameters and fragments.
- Added content fingerprints and token-similarity checks for duplicate/near-duplicate source detection.
- Added freshness parsing for ISO and common date formats.
- Added source quality scoring based on query relevance, substantive content, title presence, and freshness.
- Added bounded `rank_and_dedupe_sources()` with domain-diversity preference.
- Integrated quality selection into `BrowserCapability._execute_research_web_multi`.
- Multi-source research now inspects a bounded candidate pool before choosing the final evidence set.
- Browser research records `published_at`, `quality_score`, `quality_flags`, `freshness_timestamp`, and `canonical_url` when available.
- Final source markers are renumbered after quality filtering so synthesis sees a stable `[S1]`, `[S2]`, ... source set.

## Deliberate constraints
- No autonomous crawling.
- No LLM-based source ranking.
- No claim that freshness is known when the page exposes no parseable date.
- Low-quality/thin evidence is penalized rather than silently treated as equally strong evidence.
- Domain diversity is preferred but not absolute; bounded source count remains the primary limit.

## Validation
- `python -m compileall -q src/advi` — passed.
- Phase 35 targeted research/browser tests — 22 passed.
- Full non-blocked test suite (all `tests/test_*.py` except `tests/test_foundation.py`) — passed.
- Known external blocker remains: `tests/test_foundation.py` imports the unavailable `groq` package directly at collection time.

## Next
Phase 36 should improve temporal/source semantics at the synthesis layer: make freshness and source-quality metadata visible to the synthesizer, require conflict-aware treatment of low-quality or stale sources, and preserve evidence provenance through final answers.
