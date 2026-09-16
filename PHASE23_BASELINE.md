# Phase 23 Baseline — Model Routing & Provider Resilience

## Objective
Make LLM availability, timeout, rate-limit, malformed-response, and provider failure routing explicit without hiding programming defects.

## Implemented
- Added `src/advi/providers/router.py` with `ResilientLLMProvider`.
- Routes a request through an ordered provider chain, attempting each provider at most once.
- Falls back on normalized `LLMError` failures, including authentication, rate-limit, timeout, unavailable, and malformed/empty responses.
- Unexpected arbitrary exceptions are re-raised instead of silently switching providers, preventing real code defects from being masked.
- Records per-request provider attempts for diagnostics.
- Exported `ResilientLLMProvider` from `advi.providers`.
- Updated `src/advi/app.py` to prefer Gemini and fall back to Groq when both are configured.
- Kept the provider interface unchanged, so future local/offline providers can be inserted into the same chain without changing the brain.

## Tests
- `python -m compileall -q src/advi` — passed.
- `pytest -q tests --ignore=tests/test_foundation.py` — all tests passed.
- New `tests/test_provider_router.py` covers primary success, timeout/rate-limit fallback, malformed responses, exhausted fallback, and preservation of unexpected exceptions.

## Deliberate non-changes
- No automatic retry storm: one attempt per provider per request.
- No provider fallback around arbitrary programming exceptions.
- David remains a task/execution fallback, not an LLM transport replacement.
- No local-model implementation was invented; the routing contract is ready for one when an actual local provider is added.

## Known environment blocker
`tests/test_foundation.py` directly imports the optional Groq SDK and remains excluded from this environment's full test command when the SDK is unavailable. Existing GUI/X11 root fallback tests are outside `tests/` and were not changed.
