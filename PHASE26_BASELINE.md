# PHASE 26 — Real Capability Execution Coverage

## Objective
Exercise the concrete File, Browser, Gmail, Desktop, and Memory capabilities through their actual executor classes, using deterministic fakes/temporary resources where external GUI/network credentials are unavailable.

## Changes
- Added `tests/test_capability_execution_integration.py` covering round-trip file execution, browser navigation/read/click through a fake CDP transport, Gmail draft/read/update/send/read flows through a fake service, desktop wait through the real executor, and memory retrieval through a fake retriever.
- Hardened `FileCapability._execute_delete_file()` with resolved-path evidence and direct post-delete verification metadata.
- Hardened `BrowserCapability._execute_read_web_page()` with tab/CDP evidence metadata.
- Hardened `GmailCapability._execute_email_draft_update()` with draft-id verification evidence.
- Hardened `GmailCapability._execute_email_read()` with explicit verification evidence.
- Made Desktop executor/perception/vision imports lazy so core capability modules can be imported in headless environments without an X11 session or optional `pywinauto` installation at import time.

## Validation
- `python -m compileall -q src/advi` — PASS
- Targeted capability integration/readiness/contract tests — 16 PASS
- Full `tests/` suite excluding the documented direct-Groq blocker `tests/test_foundation.py` — 120 PASS

## Known environment limitation
The desktop capability's real GUI side effects still require a Windows desktop session (and the existing Linux environment has no X11 display). Phase 26 therefore validates the real executor logic plus dependency boundaries without pretending that GUI actions were physically exercised here.

## Deliberate non-changes
- No new capability framework or second executor layer.
- No external Gmail account access or real email sends.
- No real browser launch/navigation in CI.
- No weakening of capability policy, confirmation, verification, or fallback boundaries.
