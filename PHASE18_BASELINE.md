# ADVI Phase 18 Baseline — Failure-Aware David Fallback

## Objective
Make the David fallback path respond to classified primary-execution failures instead of acting as an unconditional second attempt.

## Changes
- Added `src/advi/brain/fallback_policy.py` with conservative hand-off decisions.
- Added `DavidFallbackGateway` adapter in `src/advi/brain/fallback_gateway.py` for the existing `FallbackService`.
- `ADVIAgent` now records the terminal failure class and consults `FallbackPolicy` before handing a failed request to David.
- Automatic hand-off is limited to `UNAVAILABLE_CAPABILITY` and `ENVIRONMENT` failures.
- `INVALID_INPUT` and `PERMISSION_DENIED` explicitly do not go to David.
- Ordinary `TASK_FAILED` and verification-related failures do not automatically repeat the task through David, reducing duplicate side-effect risk.
- A missing primary plan is treated as an unavailable-capability signal.
- David remains a separate pipeline and does not bypass ADVI's capability policy.

## Validation
- `python -m compileall -q src/advi` — PASS
- Phase 18 + Phase 2–17 focused/regression tests — PASS (73 tests)

## Deliberate non-changes
- No rewrite of the David fallback executor.
- No automatic fallback after permission denial or invalid parameters.
- No blind second execution after verification uncertainty.
- No removal of the existing fallback router/service.
- No autonomous unbounded fallback/retry loop.

## Known broader-suite environment blockers
The repository still contains earlier Phase 0 collection/environment blockers involving X11-dependent fallback tests and the direct `groq` import in `tests/test_foundation.py`.
