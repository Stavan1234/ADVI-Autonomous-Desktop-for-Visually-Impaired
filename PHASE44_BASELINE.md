# Phase 44 Baseline — Runtime Exception Containment

## Objective
Prevent startup, execution-adjacent lifecycle, and shutdown exceptions from leaving ADVI in a misleading or partially-cleaned state.

## Implemented
- Runtime startup is transactional: startup exceptions leave `started=False`, record `last_start_error`, and invoke cleanup.
- Runtime shutdown is idempotent and re-entry guarded by `_shutting_down`.
- Session-ending failures are recorded but do not prevent resource cleanup.
- Registered resources are always attempted in reverse acquisition order; one failing `close()` no longer prevents later cleanup.
- Shutdown failures are recorded in `last_shutdown_errors` while cleanup remains best-effort.
- `Runtime` now supports context-manager usage (`with Runtime(...)`).
- Existing execution/verifier boundaries already contain handler and verification exceptions; Phase 44 regression-tests those boundaries rather than swallowing unexpected programming errors.

## Tests
- `python -m compileall -q src/advi` — passed.
- Phase 44 + lifecycle/recovery/e2e targeted tests — **13 passed**.
- Full `tests/` suite excluding the pre-existing direct Groq dependency blocker (`tests/test_foundation.py`) — **all passed**.
- `pytest -q tests` still stops at collection because `tests/test_foundation.py` imports unavailable `groq` directly.

## Safety / Behavior
- Cleanup failures are visible through logs and `last_shutdown_errors`; they are not silently treated as success.
- Unexpected application/code exceptions are not converted into fake provider or user-task success.
- No automatic repair or user-action execution was added to the health/lifecycle path.

## Deferred
- Cross-session conversational continuity remains intentionally deferred.
