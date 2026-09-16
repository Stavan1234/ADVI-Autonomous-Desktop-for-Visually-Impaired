# ADVI Phase 7 Baseline — State Observation

## Objective
Give execution and verification a stable, best-effort observation layer that records relevant environment state before and after each action without allowing observation failures to break execution.

## Implemented
- Added `src/advi/core/state_observation.py`.
- Added `ObservedState`, `StateObserver`, `SystemStateSource`, `FileStateSource`, and optional `BrowserStateSource`.
- `ObservedState` is JSON-friendly and intentionally small: foreground window/HWND when supported, current application, browser URL/title, explicitly requested filesystem paths, and execution-context metadata.
- `ExecutionEngine` now captures `state_before` and `state_after` for every plan step and stores them in `ExecutionResult.metadata`.
- File observations are limited to action parameters such as `path` and `filepath`; observation is read-only.
- Browser observation supports an injected CDP client without making CDP mandatory.
- Windows-specific foreground-window inspection is lazy and guarded; headless/non-Windows environments remain safe.

## Deliberate non-changes
- No screenshot/OCR loop was added yet.
- No autonomous continuous perception loop was added.
- No direct GUI mutation is performed by observation.
- Existing `ScreenPerception` remains the semantic UI target resolver; this phase establishes the broader state snapshot contract for execution/verification.

## Validation
- `python -m compileall -q src/advi` — passed.
- Focused/regression suite — **32 passed**.

## Next architectural target
Use observed state as actual evidence for goal-level verification and replanning, including richer before/after comparisons instead of relying only on executor return values.
