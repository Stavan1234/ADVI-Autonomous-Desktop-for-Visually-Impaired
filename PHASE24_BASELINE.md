# Phase 24 Baseline — Structured Output Reliability

## Objective
Create one deterministic parsing/validation boundary for LLM structured responses so malformed, fenced, truncated-adjacent, provider-specific, or schema-invalid JSON does not cascade unpredictably through reasoning, planning, intent detection, and replanning.

## Implemented
- Added `src/advi/core/structured_output.py`.
- Added `StructuredParseResult` and `StructuredOutputError`.
- Added `parse_structured_output()` with deterministic normalization:
  - markdown/code-fence stripping;
  - extraction of a JSON object from leading/trailing provider prose;
  - trailing-comma repair;
  - safe Python-literal compatibility via `ast.literal_eval` for single-quoted object output;
  - structural type/enum/root-required validation.
- No semantic fields are invented and no repair calls another LLM.
- Integrated the parser into:
  - `ReasoningEngine`;
  - `PlannerEngine`;
  - `ReplanningEngine`;
  - legacy `IntentDetector` parsing;
  - legacy `Planner` plan parsing and next-step parsing.
- Existing subsystem normalizers remain responsible for semantic defaults/compatibility and action-level validation.

## Safety / Compatibility
- Unexpected programming exceptions are still not converted into provider fallbacks.
- Invalid structured output falls into existing deterministic subsystem fallback behavior.
- Nested legacy schema `required` fields are not enforced centrally; type/enum checks remain centralized while subsystem-specific normalization owns advisory nested slots.
- No provider-specific SDK code was added to brain components.

## Tests
- `tests/test_structured_output.py`: 7 tests.
- Full non-blocked test set: **114 passed**.
- `python -m compileall -q src/advi`: passed.
- Existing collection blocker remains `tests/test_foundation.py` importing the unavailable `groq` package directly. This is pre-existing and unrelated to Phase 24.

## Deliberately Not Done
- No second LLM repair loop.
- No automatic semantic guessing of missing fields.
- No provider-specific parsing branches in reasoning/planning code.
- No removal of the legacy `IntentDetector`/`Planner` compatibility layer.

## Result
All current structured LLM boundaries now share one deterministic parsing contract while preserving the existing subsystem behavior and fallback paths.
