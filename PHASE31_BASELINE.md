# Phase 31 Baseline — Browser Goal Workflows

## Objective
Move browser automation from individual primitives to a reliable user-level workflow: search for a query, identify a relevant result, open it, and read the resulting page.

## Implementation
- Added `research_web` as a first-class browser capability action.
- `BrowserCapability._execute_research_web()` performs a bounded search → result inspection → result selection → navigation → page-read flow.
- Result selection is deterministic and transparent: candidate links are scored using the optional target/site hint; no LLM-generated selector is executed.
- The workflow returns source URL, title, selected result metadata, content availability/length, tab identity, and CDP port as execution evidence.
- Added canonical action contract support for `research_web` with required `query` and optional `target`/`site` and bounded `max_chars`/`limit` parameters.
- Added registry semantics so the planner can see `research_web` through the authoritative capability catalogue.

## Safety / Reliability
- Empty queries are rejected.
- No active browser tab is reported explicitly as a failure.
- Missing usable result links are reported as a deterministic failure.
- Opening a selected result can succeed even when the page contains no readable text; that state is preserved in evidence rather than claimed as a readable result.
- Workflow uses existing browser navigation/read primitives and does not bypass capability policy or confirmation gates.

## Tests
- Browser workflow tests: 8 passed.
- Full non-blocked `tests/` suite: 160 passed (excluding the known direct Groq import blocker in `tests/test_foundation.py`).
- `python -m compileall -q src/advi`: passed.

## Deliberate Non-Changes
- No new general workflow engine.
- No autonomous unbounded browser loop.
- No LLM-driven DOM selector execution.
- No browser authentication automation.
- No changes to David fallback semantics.

## Next Direction
The next phase should expand real user-facing browser workflows beyond a single selected result—for example bounded multi-source research, controlled pagination, and evidence aggregation—while keeping each browser transition observable and verifiable.
