# PHASE 43 — Runtime Shutdown & Resource Lifecycle

## Objective

Make ADVI resource ownership and shutdown deterministic without introducing asynchronous or risky automatic repair behavior.

## Implemented

- Added `Runtime.register_resource()` and reverse-order best-effort cleanup.
- Runtime shutdown is idempotent and closes registered resources even when the runtime was only partially started.
- Added `close()` to `OutputManager` and `PiperTTS`; generated TTS WAV output is removed during cleanup when present.
- Added provider cleanup contract to `LLMProvider`; Gemini/Groq close their underlying clients when supported; `ResilientLLMProvider` closes providers in reverse order.
- Added Gmail service cleanup for its underlying HTTP transport when supported.
- Browser capability now terminates only the Chrome process that ADVI itself launched, avoiding interference with a user-owned Chrome process.
- Application registers output, LLM provider, Gmail service, and capability handlers with `Runtime` so lifecycle ownership is explicit.
- Fixed a latent circular import by lazily importing `TaskPersistence` inside `Runtime.start()`.

## Safety / design constraints

- Cleanup is best-effort; one failing resource cannot prevent other resources from being closed.
- No user action is executed during cleanup.
- ADVI never terminates a Chrome process it did not launch.
- SQLite stores remain stateless per-operation connections and require no persistent connection shutdown.

## Validation

- `python -m compileall -q src/advi` — PASS.
- Phase 43 lifecycle tests — 3 PASS.
- Health regression — 3 PASS.
- Full non-blocked `tests/` suite: 188 PASS.
- The known `tests/test_foundation.py` direct Groq dependency blocker remains unchanged and excluded from the non-blocked suite.
