# Phase 42 Baseline — Startup Health Validation

## Objective
Use the Phase 41 read-only health system at startup to determine whether ADVI can safely enter interactive mode, without automatic repairs or risky actions.

## Implemented
- Added `src/advi/core/startup_health.py` with `StartupHealth` and `StartupHealthValidator`.
- Added a startup decision with three states: `ready`, `degraded`, `not_ready`.
- Blocking startup conditions are limited to structural runtime/provider/task/journal failures.
- Optional capability/fallback/persistence degradation does not prevent startup.
- Attached the active `Runtime` to `ADVIAgent` so runtime health reflects the actual lifecycle state.
- `app.main()` performs a read-only startup health check with capability refresh enabled.
- Startup health never performs repair, retries, user actions, or automatic configuration changes.

## Validation
- `python -m compileall -q src/advi` — PASS.
- Phase 42 focused tests — 5 PASS.
- Health/conversation/execution regression set — 16 PASS.
- Full non-blocked `tests/` suite: PASS.
- Existing excluded blockers remain the same known environment/dependency issues: X11-dependent fallback tests and direct Groq import in `tests/test_foundation.py`.

## Deferred
Cross-session conversational continuity remains deliberately deferred due to stale-context and state-isolation risks.
