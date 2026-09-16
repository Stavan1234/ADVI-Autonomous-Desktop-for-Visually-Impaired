# ADVI Phase 17 — Capability Reliability & Failure Classification

## Objective
Give execution/recovery layers a deterministic, machine-readable distinction between invalid input, unavailable capability, permission denial, transient failure, environment failure, verification failure, genuine task failure, and unknown outcomes.

## Changes
- Added `src/advi/core/failure_classification.py`.
- Added `FailureClass` enum and `FailureClassifier`.
- `ExecutionEngine` annotates every post-execution result with `metadata.failure_class`.
- `ExecutionRecoveryPolicy` now prefers the classified failure and only auto-retries `transient` failures; it retains conservative fallback classification for legacy results.
- `ADVIAgent` includes the failure class in the replanning trigger when execution fails.
- Added deterministic unit tests in `tests/test_failure_classification.py`.

## Safety behavior
- Permission, invalid-input, unavailable-capability, environment, verification, and task failures are not treated as transient retries.
- Existing capability policy and confirmation gates remain authoritative.
- Failure classification is diagnostic/routing metadata; it does not grant execution permission.

## Validation
- `python -m compileall -q src/advi` — PASS
- Focused Phase 17 + related regression tests — PASS
- Broader Phase 2–17 regression set: **66 passed**

## Known environment blockers
The repository's pre-existing full-suite collection blockers remain unchanged:
- X11-dependent fallback tests.
- Direct `groq` import in `tests/test_foundation.py` when Groq SDK is unavailable.
