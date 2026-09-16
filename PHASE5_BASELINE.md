# Phase 5 Baseline — Bounded Replanning

## Objective

Move recovery above the executor: when a plan cannot safely continue, ADVI may ask its reasoning model for one alternative next action instead of immediately abandoning the whole task.

The executor remains authoritative. The replanner does not execute actions and cannot bypass capabilities or confirmation policy.

## Implemented

### 1. Added `core/replanning.py`

Introduced `ReplanningEngine` and `ReplanDecision`.

The replanner receives:

- original goal
- current plan
- authoritative execution history
- failed action/result
- currently available capability actions
- bounded replan count

It may return exactly one of:

- `replan` + one replacement `Action`
- `done`
- `await_user`

### 2. Bounded recovery

ADVI allows a maximum of 2 higher-level replanning attempts by default.

This prevents an uncontrolled LLM loop while still permitting an alternative execution route.

### 3. Agent integration

`ADVIAgent` now routes execution through `_execute_with_replanning()` for both normal action execution and confirmation-gated task execution.

A failed plan is therefore processed as:

`execute → inspect failure → ask replanner → validate capability → execute alternative`

rather than always:

`execute → failure → stop`

### 4. Capability authority remains in Python

A proposed recovery action must exist in the current `CapabilityRegistry` before ADVI executes it.

The model cannot invent a capability and cause execution to happen.

### 5. No automatic confirmation bypass

Replanning does not weaken the existing confirmation boundary. Consequential operations remain subject to the same system-level confirmation rules.

## Deliberately not done

- No unbounded autonomous loop.
- No direct model-controlled execution.
- No automatic retry of side-effecting actions.
- No replacement of the existing executor.
- No David merge into the core brain.
- No durable workflow database.

## Validation

Phase 5 focused + regression tests: **25 passed**.

`python -m compileall -q src/advi` passed.

The known complete-suite blockers from earlier phases remain environmental/dependency related: X11-dependent fallback tests and the direct Groq import in the legacy foundation test.
