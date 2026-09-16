# ADVI Phase 14 Baseline — Exact Confirmation Binding

## Objective
Bind user confirmation to the exact executable plan so a later confirmation cannot approve a modified action.

## Implemented
- Added `src/advi/core/confirmation.py` with `ConfirmationManager` and immutable `ConfirmationRecord`.
- Confirmation fingerprints include execution-relevant goal/action/target/focus/parameters and use canonical JSON + SHA-256.
- `ActiveTask` now stores `confirmation_fingerprint` and invalidates it on task modifications, context changes, missing-input transitions, completion, failure, and cancellation.
- `ADVIAgent` issues a fingerprint when entering `AWAITING_CONFIRMATION`.
- `task_confirm` validates the stored fingerprint against the current plan before execution.
- Stale/missing confirmation is rejected and the task returns to `IN_PROGRESS` for a fresh confirmation cycle.
- Capability policy remains authoritative; confirmation binding is an additional gate, not a replacement for policy.

## Deliberate non-changes
- No permission persistence across unrelated actions.
- No broad trust/session approval mechanism.
- No automatic confirmation of modified plans.
- No bypass of capability policy or execution verification.

## Validation
- `python -m compileall -q src/advi` — passed.
- Focused/regression suite: **27 passed**.

## Result
Confirmation is now cryptographically bound to the exact pending plan and cannot silently transfer to changed parameters.
