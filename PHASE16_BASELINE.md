# ADVI Phase 16 Baseline — Capability Hardening & Verification Adapters

## Objective
Make the capability registry a reliable contract boundary by detecting drift between registered actions, canonical action contracts, semantic metadata, and concrete handlers, while improving concrete executor evidence used for verification.

## Implemented
- Added `src/advi/core/capability_readiness.py` with a deterministic `CapabilityReadinessChecker` and structured readiness report/issues.
- Added `CapabilityRegistry.readiness_report()` as the single entry point for the audit.
- Readiness checks cover supported-action semantic metadata, canonical action contracts, verification strategy declarations, and executable handlers for available capabilities.
- Hardened `FileCapability` results with `resolved_path` evidence so filesystem verification uses the exact path actually written/read.
- Hardened `BrowserCapability` results with CDP port and tab identity metadata for later state verification/recovery.
- Added concrete verification adapters for `read_file`, `list_files`, and `read_web_page` where the executor payload itself is definitive evidence.

## Safety / architecture property
The registry remains authoritative. This phase does not create a second capability catalogue and does not let readiness checks bypass execution policy. The audit is diagnostic and deterministic; unavailable capabilities are not treated as executable.

## Validation
- `python -m compileall -q src/advi`: passed
- Focused/regression suite: **58 passed**

## Deliberate non-changes
- No new workflow engine.
- No automatic permission escalation.
- No GUI/X11 requirement introduced into core tests.
- No LLM-dependent readiness decisions.
