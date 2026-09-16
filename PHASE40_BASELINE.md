# Phase 40 Baseline — End-to-End Observability & Diagnostics

## Objective
Provide a bounded, read-only runtime diagnostic snapshot so ADVI failures can be inspected without changing task state or introducing cross-session conversational continuity.

## Deliberate scope choice
Cross-session conversational continuity was **not implemented** in this phase. It remains deferred because stale context and privacy/state carry-over can create substantial complexity. Phase 40 instead improves observability, which is safer and directly useful for debugging the existing agent.

## Implementation
Added `src/advi/core/diagnostics.py` with:
- `DiagnosticSnapshot`
- `DiagnosticsCollector`

`ADVIAgent.diagnostics()` exposes a JSON-safe snapshot containing:
- active task
- bounded recent tasks
- bounded recent execution results
- pending confirmation state
- capability availability summary
- resumed-task flag
- turn count
- current replan count
- last failure classification
- whether David fallback is available

Diagnostics are read-only and best-effort. Capability inspection failures do not interrupt ADVI operation.

## Integration
`ADVIAgent` owns a `DiagnosticsCollector` and exposes `diagnostics()` for local/debug tooling.
No new persistence layer was introduced; no sensitive conversational state is written by the diagnostics collector itself.

## Validation
- `python -m compileall -q src/advi` — PASS
- Phase 40 focused diagnostics + pipeline/provider/E2E tests — 20 PASS
- Full non-blocked `tests/` suite — PASS

Known excluded blockers remain:
1. `tests/test_foundation.py` directly imports optional `groq` SDK in this environment.
2. `test_fallback_full.py` requires X11/GUI.
3. `test_fallback_suite.py` requires X11/GUI.

## Result
Phase 40 establishes a low-risk observability foundation without implementing cross-session conversational continuity.
