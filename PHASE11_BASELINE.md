# ADVI Phase 11 Baseline — Action Semantics & Parameter Contracts

## Objective
Make planner output operationally reliable by validating and canonicalizing action parameters before execution.

## Changes
- Added `src/advi/core/action_contracts.py`.
- Defined per-action parameter contracts, required fields, aliases, and basic types.
- Planner normalizes aliases and drops materially incomplete actions.
- `ExecutionEngine.execute_action()` validates again as a final runtime guard, so non-planner callers cannot bypass contracts.
- Existing capability handlers remain authoritative for actual execution.

## Examples
- `type_text.value` -> canonical `text`.
- `save_file.filename` -> canonical `path`.
- `email_send.recipient` -> canonical `to`.
- `navigate.target` can populate `url`.
- Missing required fields produce explicit validation errors.

## Safety
Validation is intentionally separate from permissions and confirmation. It does not authorize actions and does not alter execution policy.

## Validation
Focused Phase 11 + relevant regression suite: 31 passed.
`python -m compileall -q src/advi`: passed.
