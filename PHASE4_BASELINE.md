# Phase 4 Baseline — Execution, Observation & Recovery

## Objective
Make primary execution resilient to transient desktop/browser failures without creating a second executor or uncontrolled autonomous retry loop.

## Implemented
- Added `src/advi/core/execution_recovery.py`.
- Added `StepObservation` for a structured post-attempt execution observation.
- Added `ExecutionObserver` interface for diagnostics and future brain-level replanning.
- Added `ExecutionRecoveryPolicy` with conservative, deterministic retry rules.
- `ExecutionEngine.execute_plan()` now:
  - marks plan lifecycle state (`RUNNING`, `SUCCESS`, `FAILURE`),
  - observes every execution attempt,
  - retries at most the configured number of times (default: one) for a small set of relatively safe actions when the failure appears transient,
  - never retries merely because verification is unavailable/false,
  - returns only the final attempt for each action so successful recovery is not reported as a duplicate failure,
  - records recovery metadata on recovered results.
- Removed import-time GUI coupling from `src/advi/capabilities/desktop/__init__.py` by making GUI-heavy exports lazy. `DesktopContext` can now be imported without requiring an active X11 display.

## Recovery policy
Automatically retryable actions are limited to:
- `open_application`
- `focus_window`
- `navigate`
- `search`
- `read_file`
- `wait`

The policy only retries failures classified as transient. Side-effect-heavy actions such as typing, keypresses, hotkeys, file writes, deletes, and email send are not automatically retried.

## Deliberate non-changes
- No second execution engine.
- No uncontrolled agent loop.
- No automatic retry based solely on `verified=False`.
- No LLM calls inside the execution engine.
- No bypass of confirmation, permissions, or verification.
- David remains outside the primary executor.

## Validation
Focused Phase 4 + regression tests: **20 passed**.

`python -m compileall -q src/advi`: passed.

The existing full-suite blockers from earlier phases are environmental/dependency related and are not caused by the Phase 4 changes.
