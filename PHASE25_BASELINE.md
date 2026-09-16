# ADVI Phase 25 Baseline

## Objective
Consolidate legacy intent routing around the unified `ReasoningEngine` without breaking older `ConversationEngine`, `TaskCoordinator`, and email-specific flows.

## Changes
- Added `src/advi/core/intent_bridge.py` with a one-way `ReasoningDecision -> Intent` compatibility adapter.
- Extended `ReasoningDecision` with optional `intent_hint` for feature-specific legacy compatibility only.
- Extended the reasoning schema/prompt to carry `intent_hint` without making it authoritative for routing.
- Added optional `reasoning_engine` support to `ConversationEngine` so the legacy engine can consume unified reasoning decisions instead of requiring the legacy classifier.
- Preserved the existing `IntentDetector` API for compatibility and existing tests.
- Unknown/unrecognized reasoning modes are normalized to safe non-UNKNOWN legacy intents at the bridge boundary.

## Architecture
The new brain remains authoritative:

ReasoningEngine -> Planner/Execution

For legacy consumers only:

ReasoningDecision -> intent_bridge -> Intent -> legacy handler/coordinator

Legacy `IntentType.UNKNOWN` is no longer a required route for the unified brain.

## Validation
- `python -m compileall -q src/advi` passed.
- Phase 25 focused tests: 23 passed.
- Entire `tests/` suite excluding the pre-existing `tests/test_foundation.py` blocker: all tests passed.
- `tests/test_foundation.py` remains excluded because it directly imports the optional `groq` package in this environment, as documented in earlier phase baselines.

## Deliberately Not Changed
- No deletion of legacy intent classes or APIs.
- No reintroduction of a rigid intent taxonomy into the main brain.
- No duplicate execution or safety path.
- No changes to David's architecture.
