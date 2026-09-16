# Phase 3 Baseline — Reasoning & Tool Selection

## Objective
Replace ADVI's brittle turn-level `intent -> Python router -> planner` decision with a structured reasoning decision that chooses a broad mode and optional action, while keeping Python authoritative for capability checks, permissions, execution, and verification.

## Implemented
- Added `src/advi/brain/reasoning.py` with `ReasoningEngine` and `ReasoningDecision`.
- The reasoning contract supports broad modes: conversation, task control, memory operations, action, fallback, and ask-user.
- Uses `LLMProvider.structured()` first, with a deterministic heuristic fallback when the model/provider fails.
- Invalid model modes are normalized; ADVI no longer needs an application-level `UNKNOWN` branch for this route.
- Context includes active task, recent conversation, and the authoritative capability registry.
- Added `src/advi/brain/fallback_gateway.py`, a narrow protocol boundary for the independent David fallback pipeline.
- `ADVIAgent` now routes turns through `ReasoningEngine`.
- David remains separate; the brain may invoke it for an explicit fallback decision or when the primary planner cannot materialize an executable plan.
- Fallback is not triggered merely because wording is unfamiliar.

## Deliberate non-changes
- Did not delete or rewrite the existing `IntentDetector`, `Planner`, or David services.
- Did not make David part of the primary execution engine.
- Did not add uncontrolled retry/agent loops.
- Did not change permission or verification authority.

## Validation
Focused Phase 3 + regression tests: **20 passed**.

`python -m compileall -q src/advi`: passed.

The known full-suite collection blockers from Phase 0 remain unchanged: X11-dependent fallback tests and the direct Groq import in `tests/test_foundation.py`.
