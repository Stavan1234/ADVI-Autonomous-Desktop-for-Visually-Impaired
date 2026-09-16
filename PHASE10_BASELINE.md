# ADVI Phase 10 Baseline — Planner/Reasoning Integration

## Objective
Make action planning a dedicated subsystem that consumes the upstream reasoning decision and authoritative capability registry, rather than keeping planning as a large prompt embedded inside `ADVIAgent`.

## Changes
- Added `src/advi/brain/planner.py`.
- Added `PlannerEngine` and immutable `PlanningHints`.
- `ADVIAgent` now owns `self.planner` and delegates `_generate_action_plan()` to it.
- Action vocabulary is derived only from `CapabilityRegistry`.
- Planner receives upstream reasoning hints: preferred action, rationale, and references.
- Planner validates generated actions against `CapabilityRegistry`; unavailable actions are discarded and recorded in the plan reason.
- Planner does not require a synthetic `finish` action. It only plans actions that are actually registered.
- Planner model failure returns an empty plan so existing ADVI/David fallback behavior remains available.
- Existing `ADVIAgent` call compatibility is preserved through `_generate_action_plan()`.

## Why
The architecture now has an explicit separation:

Reasoning = what kind of work / objective is needed.
Planner = how to accomplish that objective with real capabilities.
Execution = perform the resulting actions.
Observation + Verification = determine whether the outcome actually happened.
Replanning = recover when execution or verification fails.

## Validation
- Focused/regression suite: passed.
- New planner tests: passed.
- `python -m compileall -q src/advi`: passed.

## Deliberate non-changes
- No second planner/workflow engine.
- No deletion of existing fallback/David systems.
- No permission bypass.
- No automatic invention of unsupported capabilities.
