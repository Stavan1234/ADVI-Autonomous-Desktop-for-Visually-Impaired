# Phase 29 Baseline — File Modification Workflows

## Objective
Expand ADVI's real user-facing file capability beyond create/read/list/delete by providing explicit, deterministic actions for modifying an existing file.

## Implemented
- Added `append_file` to `FileCapability`.
- Added `replace_file_text` to `FileCapability`; it replaces exactly one occurrence of an explicitly supplied `old_text`.
- Added action contracts and aliases for both actions.
- Added canonical registry semantics and verification metadata for both actions.
- Added filesystem verification for appended content and replacement state.
- Kept the existing `create_file` path unchanged for backward compatibility.

## Safety / semantics
- `append_file` requires an existing file and explicit content.
- `replace_file_text` requires an existing file plus explicit `old_text` and `new_text`; it refuses to write when the target text is absent.
- Replacement is single-occurrence only, avoiding broad unintended substitutions.
- Both operations remain subject to the normal capability registry, contract validation, policy, observation, verification, recovery, and persistence layers.

## Validation
- `python -m compileall -q src/advi` — passed.
- Targeted capability/workflow suite: 29 passed.
- Full `tests/` suite excluding the known `test_foundation.py` Groq-import blocker: 145 passed.

## Known unrelated blocker
`tests/test_foundation.py` imports the optional `groq` package directly; the package is unavailable in the current environment. This remains a pre-existing environment/test dependency issue and is not caused by Phase 29.
