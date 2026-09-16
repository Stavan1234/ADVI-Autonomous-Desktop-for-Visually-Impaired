# ADVI Phase 19 Baseline — Task Lifecycle & Persistence

## Objective
Persist ADVI's first-class conversational task state across process/session boundaries while keeping persistence separate from orchestration.

## Implemented
- Added `src/advi/core/task_persistence.py`.
- Durable SQLite task snapshots use the existing ADVI memory database.
- `ActiveTask` snapshots preserve goal, entities, context, revisions, plan, execution results, status, waiting field, and timestamps.
- Resumable statuses are `in_progress`, `awaiting_input`, and `awaiting_confirmation`.
- `ADVIAgent` can restore the latest resumable task at startup when task persistence is supplied.
- Current task mutations are persisted at agent-turn boundaries and when task assignment changes.
- Terminal task state is persisted before the current-task reference is cleared.
- Confirmation approvals/tokens are never restored across process boundaries. A persisted task that was awaiting confirmation is restored as `in_progress` and marked as requiring fresh confirmation.
- Persistence failures are non-fatal and logged; the in-memory task remains authoritative for the current process.
- Added a `resumed_task` diagnostic flag to `ConversationState`.

## Deliberate non-changes
- No workflow engine.
- No background worker or scheduler.
- No durable autonomous loop.
- No automatic execution after restart.
- No persistence of secrets or approval tokens.
- Existing David architecture remains separate.

## Validation
- `python -m compileall -q src/advi` passes.
- Phase 19 + Phase 2–18 focused/regression suite: **69 tests passed**.

## Known environment blockers
The full repository suite still contains the previously documented environment collection blockers involving X11-dependent fallback tests and the direct Groq SDK import in `tests/test_foundation.py`.
