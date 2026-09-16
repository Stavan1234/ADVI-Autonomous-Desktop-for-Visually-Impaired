# ADVI Phase 9 Baseline — Closed-Loop Execution, Verification & Recovery

## Objective
Close the feedback loop between execution, observed state, goal verification, and bounded replanning. A successful executor result is not automatically treated as goal completion; uncertain verification can trigger another bounded recovery decision.

## Changes
- ReplanningEngine now accepts a recovery `trigger` and optional goal-verification evidence.
- Agent execution loop evaluates GoalVerifier after every plan execution, not only after failure-free execution.
- Goal verification states are persisted in `task.context["goal_verification"]`, including evidence.
- Execution failures trigger bounded replanning as before.
- Definitive verification failures can trigger bounded replanning.
- Verification uncertainty can trigger bounded replanning when no execution failure occurred.
- If replanning asks for user input, task transitions to AWAITING_INPUT.
- If uncertainty remains after the independent replan cap, task is retained as completed-with-uncertainty rather than falsely marked failed.
- Added an agent-side independent replan cap so a misbehaving/custom replanner cannot create an infinite loop.
- GoalVerifier treats legacy `ExecutionResult(verified=True)` as definitive verification even when older callers did not populate `verification_status`.

## Safety properties
- Replans remain bounded (default: 2).
- CapabilityRegistry remains authoritative for proposed recovery actions.
- No automatic retry of side-effect-heavy actions was added.
- No permissions or confirmation gates are bypassed.
- Uncertainty is never converted into a verified claim.

## Validation
- `python -m compileall -q src/advi` passed.
- 35 focused/regression tests passed.

## Known unrelated full-suite blockers
The same Phase 0 environment blockers remain:
- GUI/X11-dependent fallback tests require a display.
- `tests/test_foundation.py` directly imports the unavailable Groq SDK in the current environment.
