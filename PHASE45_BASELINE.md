# Phase 45 Baseline — System Integration Audit

## Objective
Audit the production ADVI request path for duplicated cognitive authorities, direct capability/policy bypasses, and compatibility code that could silently become an alternate runtime path.

## Findings and fixes
- `ADVIAgent._classify_intent()` is now a compatibility adapter over the authoritative `ReasoningEngine`; it no longer performs a second legacy LLM intent-classification call.
- Direct cognitive action branches now use a shared `_execute_authorized_action()` policy boundary before calling the low-level `ExecutionEngine`.
- Fixed a real policy bypass for `memory_forget`: the high-side-effect operation now creates a normal pending `ActiveTask`/`ActionPlan`, binds exact confirmation, and uses the same confirmation execution path as planned actions.
- `memory_update` and `memory_retrieval` also use the same policy boundary for consistency.
- The low-level `ExecutionEngine` intentionally remains policy-agnostic; policy belongs at the brain/task boundary so injected low-level executors remain reusable.
- Legacy `ConversationEngine`, `TaskCoordinator`, `TaskManager`, and `core.planner`/`core.executor` remain compatibility/test APIs rather than production entry points. The application entry point constructs `ADVIAgent` and the unified `ExecutionEngine` directly. They were not deleted because the existing test suite and compatibility surface still exercise them.

## Production path verified
`app.main()` → `Runtime` → `ResilientLLMProvider` → `ADVIAgent` → `ReasoningEngine` → `PlannerEngine` → `CapabilityPolicy` → `ExecutionEngine` → observation/verification/replanning → grounded response.

Dynamic capability refresh, task persistence, execution journaling, diagnostics, health, and fallback policy are attached to the same agent/runtime instance.

## Tests
- `python -m compileall -q src/advi` — passed.
- Phase 45 integration audit tests + policy + continuity + end-to-end scenarios — **15 passed**.
- Full `tests/` suite excluding the known direct Groq import blocker in `tests/test_foundation.py` — **all passed**.

## Deferred
- Cross-session conversational continuity remains intentionally deferred.
- Legacy compatibility modules remain until their external/test dependencies are no longer needed.
