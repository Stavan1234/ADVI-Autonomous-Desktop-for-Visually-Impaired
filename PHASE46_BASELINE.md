# Phase 46 — Full-System Audit & Human-Readable Terminal UX

## Objective
Verify the production path end-to-end, improve terminal observability without clutter, keep detailed diagnostics in `logs/advi.log`, and identify capabilities that are genuinely missing rather than assuming they work.

## Completed

### Terminal UX
- Added `src/advi/io/terminal_trace.py`.
- Each turn can display a compact bordered panel containing:
  - user input
  - reasoning route and confidence
  - concrete planner actions and compact parameters
  - execution results and verification status
  - task status
  - final ADVI response
- The renderer intentionally does **not** expose raw prompts, raw model responses, or hidden chain-of-thought.
- `ADVI_TERMINAL_TRACE=0` can disable the panel.
- Detailed pipeline/provider logs remain in `logs/advi.log`.

### Logging split
- Terminal logging defaults to `WARNING` and above.
- File logging remains `INFO` and above.
- `ADVI_CONSOLE_LOG_LEVEL` can override the terminal threshold.
- This prevents INFO-level internal traces from burying the human-readable turn panel.

### Production fallback wiring
- `app.py` now constructs `FallbackService` and wraps it in `DavidFallbackGateway`.
- David remains a separate agentic pipeline; ADVI reaches it only through the existing failure-aware fallback policy.
- Prompt files used: `src/advi/fallback/prompts/intent_prompt.txt` and `planner_prompt.txt`.

### Fallback headless/import hardening
- `fallback/executor.py` now lazily imports `pyautogui`.
- `fallback/perception.py` now lazily imports `pywinauto`.
- `fallback/vision.py` now lazily imports both GUI dependencies.
- This removes import-time X11 failures; actual desktop/vision execution still requires the real Windows desktop environment and installed dependencies.

### System audit
- Added `src/advi/core/system_audit.py` for read-only integration checks.
- Audit covers production imports, capability readiness, runtime capability state, LLM configuration, speech output assets, and speech-input status.

## Capability reality check in current test environment
- `file_management`: available and tested.
- `memory`: available when runtime SQLite memory is active; tested through existing suite.
- `browser_control`: structurally ready, but current container has no Chrome CDP connection.
- `desktop_control`: structurally ready, but current container has no Windows desktop/display.
- `email`: structurally ready, but unavailable without configured Gmail service/authentication.
- `speech_output`: Piper executable and model assets are present in the repository; actual Windows audio playback cannot be validated inside this Linux container.
- `speech_input`: **not implemented/wired into production console**. Current production interaction is keyboard text input with optional Piper speech output.
- David fallback: construction through the production gateway now succeeds without importing GUI dependencies; real desktop execution requires the user's Windows environment.

## Functional smoke check
- Fake-provider normal conversation path successfully returned an ADVI response through `ADVIAgent`.
- Runtime start/shutdown completed cleanly in the audit harness.
- David fallback gateway construction succeeded.
- `python -m compileall -q src/advi` passed.

## Tests
- `pytest . --ignore=tests/test_foundation.py`: **210 passed, 1 skipped**.
- Skipped: `scripts/test_gmail_read.py` because Gmail credentials are not configured.
- The previous direct `groq` collection blocker is still isolated in `tests/test_foundation.py`; the environment does not have the Groq SDK installed.

## Deliberately not implemented
- Cross-session conversational continuity remains deferred.
- No automatic repair/self-modifying behavior was added.
- No raw LLM chain-of-thought is displayed in the terminal.

## Conclusion
The production architecture is substantially wired and the non-blocked automated suite is green. The remaining gaps are primarily environment-dependent integrations (Windows desktop, Chrome/CDP, Gmail credentials, audio playback) plus the genuinely missing speech-input path.
