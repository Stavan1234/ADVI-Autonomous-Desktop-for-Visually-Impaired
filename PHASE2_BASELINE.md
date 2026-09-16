# ADVI — Phase 2 Context & Conversational State

Date: 2026-09-16

## Objective

Make conversational continuity explicit without creating another workflow engine.

## Changes

### 1. Added `brain/conversation_state.py`

`ConversationState` now owns:

- current conversational work item;
- bounded recent task history;
- bounded recent execution-result history;
- conversation turn count.

It deliberately does **not** own durable memory or model reasoning.

### 2. Preserved current work after execution

The previous Brain cleared `active_task` after a plan finished. The current implementation keeps the completed/failed task available as the current conversational work item and archives it in bounded recent work.

This allows follow-up requests such as modifications or continuation to still refer to the same work instead of losing the task object immediately.

### 3. New work archives old work

When a genuinely new task becomes current, the previous task is moved into `recent_tasks` automatically.

### 4. Context now exposes recent work separately

`AgentContext` now distinguishes:

- current task;
- recent work;
- recent execution results;
- recent conversation history;
- retrieved memory.

This prevents us from needing to reconstruct continuity only from a flattened goal string.

### 5. Results remain bounded

Execution results are retained in `ConversationState` as JSON-friendly dictionaries with a bounded window of 10 results.

## Deliberately not done

- No `is_terminal` capability flag.
- No new workflow/task database.
- No planner redesign.
- No intent redesign.
- No durable task persistence.
- No artifact abstraction beyond existing execution result data.
- No David integration.

Those decisions belong to later phases and will be based on actual behavioral tests.

## Tests added

`tests/test_conversation_state.py` verifies:

- completed work remains available for continuity;
- new work archives previous work;
- result history is bounded;
- context exposes current and recent work separately.

Focused Phase 2 tests: **17 passed**.

The complete suite still has the known Phase 0 collection blockers involving Linux/X11 fallback tests and the legacy direct Groq import.
