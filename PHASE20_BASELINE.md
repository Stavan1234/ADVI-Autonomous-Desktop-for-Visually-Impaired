# Phase 20 Baseline — Session Recovery & Interrupted Execution

## Objective
Make resumable tasks safe across crashes/restarts by detecting an execution step that was started but never recorded as finished, and prevent automatic replay of a potentially side-effecting action.

## Implemented
- Added `src/advi/core/execution_journal.py`.
- Durable SQLite per-step journal records task ID, plan fingerprint, step index, action fingerprint/name, start/finish status, timestamps, and serialized result.
- `ExecutionEngine.execute_plan(..., task_id=...)` journals each step before execution and marks it finished after success or terminal failure.
- Existing safe retry behavior leaves the step journaled as in-flight during the retry window, so a crash cannot silently erase the fact that the action may have happened.
- `ADVIAgent` inspects the journal when restoring a persisted task.
- An interrupted step puts the task into `AWAITING_INPUT` with `waiting_for='interrupted_execution_review'` and explicit recovery metadata.
- ADVI will not automatically replay the interrupted step.
- Explicit resume triggers a fresh planning/reassessment pass from the task goal/current context instead of replaying the old action sequence.
- Explicit cancellation safely abandons the interrupted task.
- Runtime and app wire the same SQLite database to both `TaskPersistence` and `ExecutionJournal`.
- Confirmation approvals remain non-persistent across restart.
- Added compatibility fallback for legacy/injected execution engines that do not accept `task_id`.

## Safety invariant
A crash between action start and result recording produces an `in-flight` journal entry. On restart, that evidence is treated as uncertainty about whether the side effect occurred. The action is never automatically repeated merely because the persisted task says it was still in progress.

## Validation
- `python -m compileall -q src/advi` passes.
- Focused Phase 2–20 regression suite passes: see test run in working tree.

## Deliberate non-changes
- No second workflow engine.
- No automatic replay of interrupted side-effecting actions.
- No new confirmation bypass.
- No change to David's internal architecture.
