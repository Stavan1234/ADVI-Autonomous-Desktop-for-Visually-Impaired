# Phase 28 Baseline — Adversarial Scenario Matrix & Recovery Safety

## Objective
Exercise the integrated ADVI core against adversarial conditions that unit/happy-path tests can miss, with special focus on duplicate side effects, unsafe fallback, stale approval, malformed model output, verification uncertainty, and interrupted execution.

## Changes
- Added `tests/test_adversarial_scenarios.py` with deterministic adversarial scenarios.
- Hardened `FallbackPolicy`: automatic David handoff is blocked after partial primary execution unless an explicit safe-handoff decision is supplied.
- `ADVIAgent` explicitly requests the conservative `handoff_safe=False` path for automatic fallback.

## Scenario coverage
- transient timeout retry is bounded to one retry;
- side-effecting failures are not automatically retried;
- malformed/missing action parameters are rejected before execution;
- unavailable capabilities are classified distinctly;
- permission failures never route automatically to David;
- partial primary effects block automatic David handoff;
- verification failure is distinct from execution failure;
- uncertain goal verification is not reported as verified;
- expired confirmations are rejected;
- confirmations are single-use;
- changing a plan invalidates its prior confirmation;
- replanning remains bounded even if the provider repeatedly asks to replan;
- malformed structured output fails deterministically;
- interrupted journal entries are not silently replayed.

## Validation
- `python -m compileall -q src/advi` — PASS
- Phase 28 adversarial + focused regression tests — **39 passed**
- Full `tests/` suite excluding known optional-Groq blocker `tests/test_foundation.py` — **140 passed**

## Known external blocker
`tests/test_foundation.py` directly imports the optional Groq SDK, which is unavailable in this environment. This remains a previously documented environment/dependency blocker and is not a Phase 28 regression.
