# Phase 37 Baseline — Conversational Reference Resolution

## Objective
Add deterministic resolution for common follow-up references such as "that file", "that result", "it", and "the previous one" using only bounded current/recent task, result, and research state.

## Changes
- Added `src/advi/brain/reference_resolution.py`.
- Added explicit `ConversationReference` and `ReferenceResolution` structures.
- `AgentContext` now exposes `resolved_references` to downstream reasoning prompts.
- `ADVIAgent.respond()` resolves references before reasoning/routing and asks for clarification when a concrete reference is missing or ambiguous.
- Resolution prefers current task state, then recent task/result/research evidence.
- File/result references are conservatively type-matched; ambiguous multiple candidates are not guessed.
- No new memory store, workflow engine, or semantic retrieval layer was introduced.

## Examples covered
- `append this file` -> current task's concrete file path when uniquely known.
- `use that result` -> most recent concrete execution result.
- `open that file` with multiple file entities -> clarification instead of guessing.
- ordinary messages remain unchanged.

## Validation
- `python -m compileall -q src/advi` passes.
- Targeted reference + conversation + E2E tests: 12 passed.
- Full non-blocked `tests/` suite: passes (excluding known environment/dependency blockers: root X11 fallback tests and `tests/test_foundation.py` direct Groq import).

## Deliberate non-changes
- No LLM-based reference guessing.
- No unbounded conversation-history search.
- No changes to capability policy or execution safety gates.
