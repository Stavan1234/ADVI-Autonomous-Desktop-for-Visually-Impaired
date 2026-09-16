# Phase 38 — Conversational Follow-up Semantics

## Objective
Make common conversational follow-ups deterministic where possible, while preserving the natural-language turn for the existing reasoning/planning layers.

## Implemented
- Added `advi.brain.followup_semantics.FollowUpSemantics` and `FollowUpDecision`.
- Deterministically recognizes common task modifications such as recipient/subject/tone changes and style edits.
- Deterministically recognizes task continuation phrases.
- Recognizes reference actions only when a prior reference has already been resolved; it does not guess a referent.
- Wired deterministic modification handling into `ADVIAgent` before LLM routing.
- Explicit field modifications update structured task entities and record the original instruction as a revision, automatically invalidating existing confirmation fingerprints through existing task-state mutation logic.
- Follow-up handling does not create a second memory or workflow subsystem.

## Safety / behavior
- `"change the recipient to Daniel"` becomes a structured `recipient=Daniel` task update.
- `"make it more formal"` remains a task revision rather than replacing `it` with an arbitrary context value.
- `"send that"` is not converted into an action unless a resolved reference already exists.
- Old confirmation is invalidated by task modification.

## Validation
- `python -m compileall -q src/advi` passed.
- Phase 38 targeted + relevant integration tests: 18 passed.
- `pytest -q tests --ignore=tests/test_foundation.py`: 182 passed.
- Repository root fallback tests still require X11 display and are an existing environment blocker.
- `tests/test_foundation.py` remains an existing direct optional-Groq dependency blocker when included.
