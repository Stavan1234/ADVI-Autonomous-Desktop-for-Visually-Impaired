# Phase 41 Baseline — Automated Health Checks

## Objective
Add a read-only health-check layer that detects broken runtime state, capability readiness problems, provider degradation, task-state inconsistencies, persistence/journal issues, and fallback availability without executing user actions.

## Implemented

### New module
- `src/advi/core/health.py`
- `HealthStatus`: `healthy`, `degraded`, `unhealthy`, `unknown`
- `HealthCheck`
- `HealthReport`
- `ADVIHealthChecker`

### Agent integration
- `ADVIAgent.health(refresh_capabilities=False)` returns a JSON-safe health report.
- Capability refresh is opt-in; health inspection itself does not repeatedly invoke environment/authentication probes.

### Checks
- Runtime lifecycle state
- LLM provider configuration / recent resilient-provider attempts
- Current task consistency, including confirmation binding and interrupted-task review state
- Capability readiness and current availability
- Task persistence database reachability
- Execution journal consistency for the active plan
- David fallback availability

## Design constraints
- Read-only with respect to user actions.
- No LLM call is made by health checks.
- Health checks do not bypass capability policy, confirmation, or verification.
- Missing optional subsystems are reported as degraded rather than crashing the agent.
- Capability readiness remains diagnostic; it does not mutate capability semantics.

## Validation
- `python -m compileall -q src/advi` — PASS
- Phase 41 focused + diagnostics + capability/recovery regression tests — 16 PASS
- Full `tests/` suite excluding the existing direct Groq dependency blocker (`tests/test_foundation.py`) — PASS

## Known unrelated blockers
The full repository still has the historical environment/dependency blockers when collection includes everything:
- root fallback tests require a GUI/X11 display
- `tests/test_foundation.py` directly imports the optional Groq SDK in this environment

## Deferred
Cross-session conversational continuity remains intentionally deferred. Health checks are diagnostic only and do not persist new conversational context.
