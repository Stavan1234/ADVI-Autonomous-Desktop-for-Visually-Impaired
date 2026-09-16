# ADVI Phase 15 Baseline — Permission Lifetime & Trust Scope

## Objective
Ensure user approval is scoped to one exact plan, expires, and is single-use. A previous approval must never silently authorize a modified or newly replanned action.

## Implemented
- Extended `ConfirmationRecord` with `issued_at` and `expires_at`.
- `ConfirmationManager` now provides a bounded default TTL of 300 seconds.
- Confirmation fingerprints remain exact-plan bindings.
- Confirmations are single-use through `consume()` and an internal consumed-fingerprint set.
- `validate()` rejects missing, changed, consumed, expired, and future-dated approvals.
- `ActiveTask` stores confirmation timing metadata and clears it on task mutation/state transitions.
- `ADVIAgent` validates and consumes approval before execution.
- Recovery/replanning plans are independently checked by `CapabilityPolicy`.
- If a recovery action requires confirmation, the task pauses with a new exact-plan confirmation rather than inheriting the original approval.
- Replan count is preserved across a confirmation pause so the bounded recovery limit cannot reset accidentally.

## Safety property
Approval scope is now:

`one exact executable plan + one bounded time window + one execution authorization`

Changing parameters, modifying the task, generating a new recovery plan, or allowing the approval window to expire invalidates the previous approval.

## Validation
- Focused/regression suite: **39 passed**
- `python -m compileall -q src/advi`: passed

## Deliberate non-changes
- No persistent permission database.
- No broad “trust this application forever” mode.
- No permission escalation through David/fallback.
- Capability policy remains authoritative.
