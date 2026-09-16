# ADVI Phase 21 Baseline — Unified Capability/Tool Semantics

## Objective
Make the runtime CapabilityRegistry the single authoritative source for executable action semantics exposed to reasoning, planning, policy, and diagnostics, while preserving compatibility with legacy capability self-awareness APIs.

## Implemented
- Added `ActionSpec` in `src/advi/capabilities/registry.py` as the canonical composed runtime view of an executable action.
- Added `Capability.action_spec()`, `CapabilityRegistry.get_action_spec()`, and `CapabilityRegistry.list_action_specs()`.
- `CapabilityRegistry.actions_for_prompt()` now renders from `ActionSpec` instead of rebuilding action semantics independently.
- `CapabilityPolicy` now evaluates `ActionSpec` directly instead of consuming a duplicated metadata dictionary.
- Capability-level runtime self-awareness prompt adapter added as `capability_for_registry_prompt()` while preserving the existing legacy helper for compatibility.
- Capability-level prompt no longer duplicates individual action names; action-level semantics are owned by `ActionSpec`/`actions_for_prompt()`.
- Readiness diagnostics still explicitly detect missing canonical action contracts; this remains intentional because contracts are the validation source for parameter shape.

## Validation
- `python -m compileall -q src/advi` passed.
- Phase 21 + Phase 2–20 focused/regression suite: **64 tests passed**.

## Deliberate non-changes
- No removal of legacy `src/advi/core/capabilities.py`; its public API remains for compatibility.
- No new executor or workflow engine.
- No change to permission/confirmation behavior.
- No relaxation of registry availability checks.

## Architectural result
Reasoning/planning/policy now consume the same runtime action specification instead of independently reconstructing tool semantics. Parameter validation remains centralized in `action_contracts.py`, while `ActionSpec` is the unified consumer-facing action definition.
