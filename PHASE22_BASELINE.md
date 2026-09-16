# ADVI Phase 22 Baseline — Dynamic Capability Availability

## Objective
Make capability availability a live runtime property, refreshed before reasoning and again at the execution boundary, while preserving the CapabilityRegistry as the authoritative source of capability semantics.

## Changes
- Extended `Capability` with a short `availability_ttl_seconds` cache window.
- Added `CapabilityRegistry.refresh_stale()` for lazy, TTL-based runtime probes.
- Added `CapabilityRegistry.refresh_for_action()` for action-specific refreshes immediately before execution.
- Kept explicit `set_status()`, `refresh_capability()`, and `refresh_all()` APIs for deterministic overrides and startup checks.
- `ADVIAgent.respond()` now refreshes stale capability state before assembling reasoning context.
- `ExecutionEngine.execute_action()` refreshes the owning capability before enforcing availability and executing.
- Existing availability probes remain read-only/best-effort and publish status + reason + timestamp.

## Runtime behavior
- AVAILABLE and PARTIAL remain executable states; UNAVAILABLE actions are excluded from executable specs.
- Fresh probe results are reused for the configured TTL to avoid probing OS/browser/auth state on every prompt.
- A malformed/missing timestamp is treated as stale and safely re-probed.
- Capability discovery, planner selection, policy, fallback, and execution continue to share the same registry state.

## Validation
- `python -m compileall -q src/advi` — PASS
- Phase 2–22 focused regression suite — 75 tests passed

## Deliberate non-changes
- No second capability registry.
- No LLM-driven availability decisions.
- No automatic application launches/auth flows from probes.
- No changes to permission/confirmation semantics.
- David remains outside the primary capability registry and cannot bypass policy.

## Known broader-suite blockers
The pre-existing environment blockers from Phase 0 remain: GUI/X11-dependent fallback tests and the foundation test's direct Groq SDK import.
