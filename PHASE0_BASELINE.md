# ADVI — Phase 0 Baseline

Date: 2026-09-16

## Purpose

Establish a reproducible baseline and remove only foundation-level import/dependency problems that prevent ADVI from being inspected or tested.

## Environment checked

- Python: 3.13.5
- `pyproject.toml`: present and parseable
- Package name: `advi-desktop-agent`
- Console entry point: `advi.app:main`
- Python requirement: `>=3.13,<3.14`

## Baseline findings

### Source integrity

- `compileall` passes for the full `src/advi` tree.
- `import advi` passes.
- Core runtime/action/execution/registry/memory modules import successfully.

### Optional dependency isolation

The original package imported provider and Gmail SDKs eagerly. This meant a missing optional SDK could make `advi.app` / `ADVIAgent` unimportable.

Phase 0 changes make these SDKs load only when their provider/integration is actually instantiated or used.

Verified after change:

- `import advi.app` — OK
- `import advi.brain.agent` — OK
- `import advi.providers` — OK
- `import advi.integrations.gmail` — OK

### Dependency manifest alignment

Both `pyproject.toml` and `requirements.txt` now declare packages used directly by the source tree that were previously missing from the manifests:

- google-genai
- pydantic
- pyautogui
- websocket-client
- pillow
- pytesseract

### Packaging

A wheel was successfully built with:

`python -m pip wheel . --no-deps --no-build-isolation`

The earlier isolated build attempt failed only because the execution environment cannot reach PyPI to download build dependencies.

### Tests

Focused tests currently runnable in this Linux environment:

`22 passed`

Full-suite collection still stops on environment/platform-specific tests:

1. fallback tests import `pyautogui` and require an X11 display, which is unavailable in this environment;
2. `tests/test_foundation.py` imports the Groq SDK directly.

These are not being “fixed” in Phase 0 by masking them. The full test suite will be rebuilt around the current production architecture in the appropriate later phase.

## Phase 0 exit condition

The ADVI source is syntactically valid, package metadata is buildable, core modules can import without optional provider/Gmail SDKs, and the current runnable test subset is green.

## Deliberately not changed

- Brain/task architecture
- Intent/planner design
- Capability semantics
- David fallback internals
- Legacy deletion
- Verification redesign
- Memory architecture
