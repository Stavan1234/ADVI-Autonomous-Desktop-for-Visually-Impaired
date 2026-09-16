# Phase 27 Baseline — End-to-End Task Scenarios

## Objective
Exercise realistic ADVI requests through the complete agent pipeline: reasoning -> planning -> capability policy -> execution -> observation -> verification -> recovery/confirmation.

## Implemented
- Added `tests/test_end_to_end_scenarios.py` covering:
  - file creation through Agent -> ReasoningEngine -> PlannerEngine -> ExecutionEngine -> filesystem verification
  - confirmation-gated email send through two user turns
  - multi-turn task modification and re-planning using the retained current task
  - unavailable primary capability handling without blank/crashing output
- Fixed confirmed-plan execution so an already-consumed exact confirmation is not requested a second time during execution.
- Fixed empty/invalid planner results so action requests produce an explicit executable-capability response instead of a blank direct-conversation response.
- Moved the missing-information gate before the empty-action case so planner-generated missing information remains actionable.

## Validation
- `python -m compileall -q src/advi` passes.
- Full `tests/` suite excluding the known direct-Groq-import blocker `tests/test_foundation.py` passes.

## Deliberate scope
This phase adds scenario coverage and fixes integration defects exposed by those scenarios. It does not add a new workflow engine or change David's architecture.
