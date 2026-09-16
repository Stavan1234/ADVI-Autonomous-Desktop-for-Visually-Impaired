# Phase 8 Baseline — Goal Verification & Evidence Reasoning

## Objective
Use the state observations introduced in Phase 7 as explicit evidence for goal-level outcome assessment, while keeping execution completion separate from verification certainty.

## Changes
- Added `src/advi/core/goal_verification.py`.
- Added `GoalVerificationStatus`: `verified`, `failed`, `uncertain`.
- Added `GoalVerification` structured outcome with evidence and reason.
- Added `GoalVerifier` to aggregate action execution/verification results conservatively.
- Wired `ADVIAgent` to evaluate a completed execution run through `GoalVerifier`.
- A goal is marked failed only on definitive failure; successful execution may still be marked completed when evidence is uncertain, while the uncertainty is retained in task context as `goal_verification`.
- This keeps task lifecycle state compatible with existing `ActiveTask` statuses while preserving truthful response generation from Phase 6.

## Deliberate non-changes
- No LLM-based verifier was added.
- No autonomous endless verification loop.
- No action is retried because verification is merely uncertain.
- No executor-side mutation was added to the observation layer.

## Validation
- `python -m compileall -q src/advi` passed.
- Phase 8 + previous phase focused/regression suite: **35 passed**.

## Known full-suite blockers
The same pre-existing Phase 0 environment blockers remain:
1. X11-dependent fallback tests.
2. `tests/test_foundation.py` direct `groq` import in the current environment.

These are not Phase 8 failures.
