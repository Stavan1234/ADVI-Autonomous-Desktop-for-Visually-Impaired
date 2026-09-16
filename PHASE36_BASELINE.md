# Phase 36 Baseline — Temporal & Source-Aware Synthesis

## Objective
Make research synthesis actually use source quality/freshness metadata and treat stale, freshness-unknown, thin, and conflicting evidence explicitly.

## Changes
- Extended `ResearchSource` with `quality_score`, `quality_flags`, and `freshness_timestamp`.
- Research synthesis prompt now exposes quality/freshness metadata and instructs the model to prefer higher-quality and fresher evidence for time-sensitive questions.
- Time-sensitive questions are detected deterministically for terms such as latest/current/today/recent/as-of/price/weather/score/status and year references.
- Synthesis adds explicit uncertainty when freshness is unknown, a source is flagged stale, or a source has thin content.
- Invalid/empty source-claim mappings remain rejected; missing mappings add an uncertainty note.
- Existing evidence ordering and conflict detection remain intact; conflicts are still surfaced rather than silently reconciled.

## Deliberate non-changes
- No external source trust ranking was invented.
- No automatic claim-level truth scoring was added.
- No additional LLM repair call was introduced.
- Conflicting sources are not arbitrarily resolved by the system.

## Validation
- `python -m compileall -q src/advi` — passed.
- `pytest -q tests/test_research_synthesis.py tests/test_research_quality.py` — 10 passed.
- Full non-blocked repository suite excluding known legacy blockers (`tests/test_foundation.py`, `test_fallback_full.py`, `test_fallback_suite.py`) — 170 tests passed.

## Known legacy blockers
- `tests/test_foundation.py` directly imports optional `groq` dependency unavailable in this environment.
- `test_fallback_full.py` and `test_fallback_suite.py` require an X11/GUI environment.
