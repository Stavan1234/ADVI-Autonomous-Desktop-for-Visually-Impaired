# ADVI Phase 13 Baseline — Capability Policy & Safety Enforcement

## Objective
Centralize capability-level side-effect and confirmation decisions so planning cannot bypass system policy and safety requirements are not duplicated in `ADVIAgent`.

## Implemented
- Added `src/advi/core/capability_policy.py`.
- Added `CapabilityPolicy`, `PolicyDecision`, and `PolicyDisposition` (`ALLOW`, `CONFIRM`, `DENY`).
- Policy reads authoritative action semantics from `CapabilityRegistry`.
- Unavailable/unregistered actions are denied.
- Registry-declared confirmation requirements force confirmation.
- Critical side-effect actions require confirmation even if an LLM planner omits it.
- `ADVIAgent._plan_and_execute_task()` now delegates permission/confirmation gating to `CapabilityPolicy`.
- Removed the agent-local hard-coded `_REQUIRES_CONFIRMATION` set.
- Existing task confirmation flow remains intact; this phase changes the source of truth, not the user interaction contract.

## Deliberate non-changes
- No automatic approval of critical actions.
- No permission bypass for David/fallback.
- No changes to executor behavior.
- No persistent permission database or user policy editor yet.

## Validation
- `python -m compileall -q src/advi` — PASS
- Focused/regression suite: **35 passed**
  - conversation state
  - pipeline trace
  - structured intent
  - planner/intent data
  - email composition
  - planner engine
  - execution recovery
  - goal verification
  - replanning
  - capability policy

Known Phase 0 full-suite collection blockers remain unchanged: X11-dependent root fallback tests and the direct `groq` import in `tests/test_foundation.py`.
