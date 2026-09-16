# Phase 12 Baseline — Tool / Capability Semantics

## Objective
Give ADVI's authoritative capability registry richer semantics for action selection, parameter requirements, side effects, confirmation, and verification expectations.

## Changes
- Extended `Capability` with action-level semantic metadata through `action_metadata()`.
- Added authoritative `_ACTION_SEMANTICS` for registered action names.
- Reused `ActionContract` parameter definitions so the planner sees required parameters, kinds, and aliases from the same validation source.
- Added `CapabilityRegistry.get_action_metadata()`.
- Added `CapabilityRegistry.actions_for_prompt()` for a detailed action catalogue.
- Updated `PlannerEngine` to consume the detailed authoritative catalogue rather than action names alone.

## Safety
- Capability availability remains authoritative.
- Existing parameter validation remains authoritative at planner and execution boundaries.
- Confirmation-sensitive actions are marked accordingly in semantics.
- No executor behavior was changed in this phase.

## Validation
- Focused/regression suite: 33 passed.
- `python -m compileall -q src/advi`: passed.

## Deliberate non-changes
- No new workflow engine.
- No automatic side-effect policy rewrite.
- No GUI/vision implementation.
- No replacement of existing executors.

## Next
Use capability semantics in action selection/replanning and eventually enforce richer policy at the execution boundary once each capability's real behavior is fully mapped.
