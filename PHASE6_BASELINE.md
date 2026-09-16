# Phase 6 Baseline — Verification Contract & Honest Outcomes

## Objective

Make verification an explicit evidence contract so ADVI distinguishes an action that executed from an action whose resulting state is actually verified.

## Implemented

### 1. Explicit verification state

`ExecutionResult` now carries `verification_status` with three states:

- `verified` — the verifier has positive evidence the requested state exists.
- `failed` — the verifier found definitive evidence the expected state was not achieved.
- `uncertain` — execution may have succeeded, but the system cannot independently establish the final state.

The existing `verified` boolean is retained for compatibility.

### 2. Verifier semantics

`ActionVerifier` now consistently maps verification outcomes into the three-state contract.

A missing verifier or verifier exception does **not** fabricate success or failure; it produces `uncertain` while preserving the executor's success unless there is definitive evidence of failure.

### 3. Aggregate verification summary

`ActionVerifier.summarize()` provides a task-level evidence summary for downstream reasoning and diagnostics.

### 4. User-facing response honesty

`ADVIAgent` no longer treats every successful-but-unverified action as fully verified. It explicitly tells the user when the requested actions were executed but the final state could not be independently confirmed.

## Deliberately not done

- No fake verification for actions without a real state checker.
- No automatic retry based solely on uncertainty.
- No LLM-generated claims of success.
- No broad screen-understanding implementation yet.

## Validation

Phase 6 focused + regression tests: **30 passed**.

`python -m compileall -q src/advi` passed.

The known full-suite blockers remain the same Phase 0 environment/dependency issues.
