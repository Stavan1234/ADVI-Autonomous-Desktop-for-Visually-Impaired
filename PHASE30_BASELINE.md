# Phase 30 — Browser Workflow Hardening

## Objective
Harden the existing CDP browser workflows as real user-facing capability paths: navigation, search, click, and page reading.

## Changes
- Added `CDPBrowser.evaluate_script()` and `CDPBrowser.navigate_tab()` compatibility aliases used by the browser executor.
- Navigation records actual tab URL/title when available instead of assuming the requested URL is the final state.
- Browser search records current URL and target-tab evidence.
- Web-element clicks now fail explicitly when the selector is not found and capture before/after tab state.
- Page reads record URL/title and correctly mark non-string payloads as unsuccessful.
- Added dedicated browser workflow regression tests.
- Optional tab metadata enrichment remains backward-compatible with simple/fake CDP adapters.

## Safety / reliability
- Browser actions still pass through contracts, capability policy, execution, observation, and verification.
- Click failure is explicit and cannot be reported as success merely because the executor returned without raising.
- Browser state evidence is attached to `ExecutionResult.metadata` for verification and replanning.
- No automatic browser side-channel or policy bypass was introduced.

## Validation
- Browser workflow + relevant recovery/regression tests: 49 passed.
- Full `tests/` suite excluding the pre-existing direct Groq dependency blocker in `tests/test_foundation.py`: all tests passed.
- `python -m compileall -q src/advi`: passed.
