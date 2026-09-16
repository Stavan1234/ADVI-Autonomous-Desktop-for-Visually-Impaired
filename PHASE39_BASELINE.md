# Phase 39 Baseline — Multi-Turn Task Continuity

## Objective
Stress task continuity across realistic multi-turn sequences so current work, revisions, references, confirmation, persistence, and terminal archival remain coherent.

## Changes
- `ADVIAgent.active_task = None` now archives the current task through `ConversationState.clear_current_task(archive=True)` instead of dropping it silently.
- Added `tests/test_multiturn_continuity.py` covering completed-task archival, create→modify continuity, confirmation invalidation after modification, and persisted multi-turn state.

## Behavioral Contract
- A task keeps the same `task_id` across normal follow-up modifications.
- Revisions accumulate without overwriting the canonical goal.
- Any task mutation invalidates prior confirmation.
- Persisted resumable state restores entities/revisions/plan/results.
- A cleared terminal task remains in bounded recent-task history for conversational reference.
- Old confirmation tokens are never restored across process boundaries.

## Validation
- Phase 39 continuity + regression tests: 22 passed.
- Full `tests/` suite excluding the known direct-Groq blocker `tests/test_foundation.py`: 184 passed.
- `python -m compileall -q src/advi`: passed.

## Known External Blocker
`tests/test_foundation.py` directly imports the optional `groq` package in this environment and remains excluded from the non-blocked suite.
