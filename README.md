### Shadow — Sequential Focus Areas

1. **Project Foundation & Runtime Setup**
2. **Core I/O: Text + Voice Input/Output**
3. **Normal Conversation Engine**
4. **Conversation State & Context**
5. **Short-Term Memory**
6. **Long-Term Memory & Session Continuity**
7. **Personality, Identity & Principles**
8. **Self-Model / Capability Awareness**
9. **Intent Understanding**
10. **Planner & Task Reasoning**
11. **Execution State / Task Manager**
12. **LLM Observability & Debugging Console**
13. **LLM Cost, Token & Latency Analysis**
14. **Permission & Confirmation Framework**
15. **Gmail / Email Intelligence**
16. **File Intelligence & File Operations**
17. **Application Control**
18. **GUI / Screen Understanding & Automation**
19. **Browser Automation**
20. **Verification, Recovery & Rollback**
21. **Tool Registry & Capability System**
22. **Model Routing & Offline Fallbacks**
23. **Central Logging & Error Intelligence**
24. **Testing & Reliability Infrastructure**
25. **Performance & Resource Optimization**
26. **Autonomous Multi-Step Workflows**
27. **Continuous Self-Monitoring / Self-Reflection**

**Rule:** one focus area at a time; don't move forward until the current subsystem is genuinely understood, tested, and stable.





# Final ADVI recovery plan

## Phase 0 — Freeze the foundation

Do **not** rewrite:

```text
GmailService
Gmail OAuth
LongTermMemory
MemoryRetriever
ShortTermMemory / SessionBuffer
Piper
Telemetry
Config / Runtime
GroqProvider
GeminiProvider
Executor's low-level tool methods
```

They are not the core architectural problem.

The current repository is already substantial. The current `Executor` is particularly useful because it has the right result contract:

```text
action
success
data
error
```

We keep that.

---

# Phase 1 — Fix the LLM boundary completely

Before rebuilding orchestration, make Gemini reliable enough to be part of an agent loop.

### 1.1 Gemini must return structured data reliably

Current problem:

````text
valid JSON
→ ```json ... ```
→ parser failure
→ UNKNOWN
````

and sometimes:

```text
partial JSON
→ parser failure
→ UNKNOWN
```

This already caused:

* task modification → `unknown`
* email send → `unknown`
* information request → `unknown`

### Fix

Move structured-output responsibility into the Gemini provider / structured-call layer:

```text
Gemini
 ↓
JSON/schema response
 ↓
Pydantic/dataclass validation
 ↓
Intent / Plan / Decision
```

Do not scatter JSON cleanup around `ConversationEngine`.

Add one reusable structured-output mechanism.

### 1.2 Separate normal Gemini chat from structured Gemini calls

The provider currently has only:

```text
chat(messages)
```

We should eventually have the conceptual capability for:

```text
chat(...)
structured(...)
```

because these are different jobs.

Gemini should not be forced to produce ordinary conversational text when we need strict JSON.

### 1.3 Measure latency

The current intent calls reached roughly 20–50 seconds in real tests.

After fixing the structured call, measure:

```text
intent latency
planner latency
Groq latency
total
input tokens
output tokens
```

Do not optimize blindly.

---

# Phase 2 — Simplify Intent, don't destroy it

Your instinct here was correct:

**Intent is important.**

But its job needs to be narrower.

Currently `IntentType` contains a mixture of:

```text
semantic intent
task control
email operations
conversation
system actions
```

That makes the prompt huge.

We should keep the existing model initially, but evolve it toward:

```text
Intent
 ├── goal/type
 ├── target
 ├── entities
 ├── parameters
 ├── confidence
 └── execution_mode
```

The exact field `execution_mode` is optional at first, but I recommend planning for it.

Examples:

```text
conversation
information
tool
interactive_agent
```

This gives us the future desktop distinction you raised.

### Example

Current Gmail:

```text
goal = send_email
execution_mode = tool
```

Future browser automation:

```text
goal = send_email
execution_mode = interactive_agent
```

The intent tells the system **what kind of workflow this is**.

It does not execute anything.

---

# Phase 3 — Replace the fake Planner with a real Planner

This is the biggest change.

Current:

```text
Intent
 ↓
IntentType → action mapping
 ↓
one PlanStep
```

That is not enough.

The existing `Plan` and `PlanStep` structures are actually fine. We don't need `ActionPlan` as a new duplicate class.

Make the existing `Planner` produce:

```text
Plan
 ├── goal
 ├── confidence
 ├── steps[]
 └── status
```

with multiple steps.

### Example: email

```text
Goal: send_email

1. resolve_recipient
2. compose_email
3. create_email_draft
4. read_email_draft
5. await_confirmation
6. send_email
7. verify_send
```

This is where David's old code gives us a useful idea: his planner explicitly produces a sequence of actions rather than leaving workflow construction to Python. That's the part worth borrowing, not the whole old architecture.

---

# Phase 4 — Define the meaning of a PlanStep

This is extremely important.

A plan step should specify something like:

```text
action
parameters
reason
executor type
```

The executor type is future-proofing.

For example:

```text
resolve_recipient
    executor = python_tool

compose_email
    executor = groq_generation

create_email_draft
    executor = python_tool

await_confirmation
    executor = user_boundary

send_email
    executor = python_tool

desktop_click
    executor = interactive_agent
```

This is how we support David's future implementation cleanly.

We don't need a completely different architecture for browser automation.

---

# Phase 5 — Change Task from "list of actions" to "plan progress"

We already have `Task`.

Keep it.

Extend it so it owns:

```text
task_id
goal
plan
current_step
status
context
```

The important part is:

**Plan and Task must no longer duplicate execution state.**

The plan describes the workflow.

The task stores where we currently are in that workflow.

Example:

```text
Task:
    status = AWAITING_CONFIRMATION
    current_step = 4

Plan:
    0 resolve_recipient      completed
    1 compose_email          completed
    2 create_draft            completed
    3 readback                completed
    4 await_confirmation      waiting
    5 send_email              pending
    6 verify_send             pending
```

---

# Phase 6 — Turn TaskCoordinator into the actual execution loop

This is where the architecture finally becomes agentic.

The current `TaskCoordinator.run()` executes essentially the whole plan loop itself.

We need to change its responsibility to:

```text
receive / create plan
 ↓
execute ONE current step
 ↓
record result
 ↓
ask Planner what happens next
```

Conceptually:

```python
while task.status == RUNNING:

    decision = planner.update_plan(
        intent,
        task,
        previous_result,
    )

    if decision == WAIT_FOR_USER:
        break

    step = task.plan.steps[task.current_step]

    result = executor.execute(step)

    task.record(result)

    if step requires replan:
        continue
```

But **don't implement a Python `while` loop that blindly executes every step without planner involvement**.

The planner gets the execution result after each step.

That is the important part.

---

# Phase 7 — Planner feedback loop

This is the central loop you wanted.

Example:

### Gemini Planner

```text
Step:
create_email_draft
```

Python:

```text
SUCCESS
draft_id = abc123
```

Then send to Gemini:

```text
Current goal:
send email

Completed:
resolve_recipient
compose_email
create_email_draft

Execution result:
SUCCESS
draft_id=abc123

Current step:
create_email_draft

What should happen next?
```

Gemini returns:

```text
next step = read_email_draft
```

Python executes that.

Then Gemini gets the result.

Repeat.

---

# Phase 8 — Plan modification / replanning

This is the reason we're doing this properly.

Suppose current plan:

```text
1 resolve recipient ✓
2 compose email     ✓
3 create draft      ✓
4 confirmation      WAITING
5 send              pending
```

User says:

> Make it more polite and add that I'll be back Monday.

Intent detects:

```text
TASK_MODIFICATION
```

But we do **not** hard-code an email-specific modification routine.

Instead:

```text
Current Task
+
Current Plan
+
Current Draft
+
User modification
        ↓
Gemini Planner
        ↓
Updated Plan
```

Maybe:

```text
1 resolve recipient ✓
2 compose email     MODIFY
3 update draft      NEW
4 readback          NEW
5 confirmation
6 send
7 verify
```

Already-completed work stays completed.

That's the whole point of persistent planning.

---

# Phase 9 — Confirmation becomes a genuine plan boundary

This is one of the strongest decisions from our discussion.

Confirmation should be a step:

```text
await_confirmation
```

not a parallel mini-framework.

When the planner reaches it:

```text
Task.status = AWAITING_CONFIRMATION
```

and execution stops.

Then the user can say:

```text
yes
send it
make it more polite
read it again
cancel
pause
```

Intent interprets what the user means **relative to the current plan**.

Planner decides how the plan changes.

This removes much of the current special-case routing.

---

# Phase 10 — Groq's role

Groq should **not** be the executor.

It should be used for language work.

### Groq can:

* draft email text
* improve wording
* read back drafts
* ask confirmation naturally
* explain errors
* produce final conversational answers

### Groq cannot:

* claim Gmail succeeded without execution evidence
* decide whether a file was actually deleted
* decide whether an action completed
* directly mutate task state

The clean rule is:

```text
Gemini = decide WHAT happens next
Groq = decide HOW to say it
Python = determine WHAT actually happened
```

---

# Phase 11 — Future desktop/browser executor

This is where your LLM ping-pong requirement belongs.

For current Gmail API:

```text
Gemini
 ↓
one tool step
 ↓
Python
 ↓
result
 ↓
Gemini
 ↓
next step
```

For David's future desktop agent:

```text
Gemini
 ↓
click/type/navigate action
 ↓
Desktop Agent
 ↓
screen observation
 ↓
Gemini
 ↓
next action
 ↓
Desktop Agent
 ↓
observation
 ...
```

That can be selected by the plan step's executor type.

So **we don't build two architectures**.

We build one planner/executor protocol that supports:

```text
Python tool executor
LLM-generation executor
Interactive desktop executor
```

---

# Phase 12 — Email becomes our flagship workflow

Before migrating anything else, make Gmail perfect.

Final workflow:

```text
User
 ↓
Intent
 ↓
Plan
 ↓
Resolve recipient
 ↓
Compose content
 ↓
Create Gmail draft
 ↓
Read draft
 ↓
Await confirmation
 ↓
[USER CAN MODIFY]
 ↓
Update draft
 ↓
Read draft again
 ↓
Await confirmation
 ↓
Send
 ↓
Verify send
 ↓
Completed
```

### Cases we must support

**Known recipient**

```text
Joel → joel@example.com
```

**Unknown recipient**

```text
David → ask user for email
```

**Missing subject**

Either:

* planner/Groq generates one, or
* ask user, depending on policy.

We should not currently let `Executor` fail simply because the planner forgot to generate a subject. That's a planning failure we should resolve upstream.

**Modification**

```text
make it more polite
```

updates the existing draft.

**Cancellation**

```text
don't send it
```

ends task.

**Confirmation**

```text
yes
```

moves to `send_email`.

**Send failure**

```text
FAILED
```

and ADVI explicitly says it failed.

---

# Phase 13 — Execution truth becomes absolute

This is the critical Claude fix.

The system must guarantee:

```text
ExecutionResult.success = False
        ↓
No success claim
```

Not through a prompt alone.

The application should construct the final conversational context from verified execution state.

Groq gets:

```text
AUTHORITATIVE RESULT:
email_send
success = false
error = ...
```

Then it can phrase it naturally.

This is much stronger than saying:

> "Please don't hallucinate."

---

# Phase 14 — Fix information requests

The current system correctly identifies:

```text
information_request
```

but the planner blocks it.

We need two broad classes of work:

### Tasks

Need Executor/Plan.

```text
send email
open browser
modify file
```

### Responses

Do not need Executor.

```text
what is 2+2?
who are you?
what do you remember?
```

The planner should explicitly know whether something is:

```text
requires_execution = true/false
```

Again: no giant new class necessary.

---

# Phase 15 — Reduce ConversationEngine dramatically

Once the new loop works, `ConversationEngine` should lose:

* email-specific continuation
* email confirmation logic
* email modification logic
* pause heuristics
* task routing
* execution-specific branching
* post-hoc success prompts

It should mostly:

```text
receive user message
→ invoke agent flow
→ generate/return response
```

That will probably cut it dramatically below its current ~870 lines.

---

# Phase 16 — Remove redundant TaskCoordinator logic

Current coordinator contains direct:

```text
gmail.send_draft()
gmail.update_draft()
gmail.get_draft()
```

Those should disappear from the coordinator.

Coordinator should say:

```text
Executor.execute(step)
```

That's it.

The coordinator manages workflow, not Gmail.

---

# Phase 17 — Fix TaskManager cleanup

The current code already has a real problem:

`TaskStatus` is declared twice.

That must be cleaned up.

Also:

```text
TaskManager
TaskCoordinator
```

should have a single ownership rule:

### TaskManager

State mutations.

### TaskCoordinator / Agent loop

Workflow decisions.

### Executor

Actions.

### Planner

Planning.

No overlap.

---

# Phase 18 — Structured Gemini planning

Once the plan model is stable, Gemini should produce schema-validated plans.

For example:

```json
{
  "goal": "send_email",
  "steps": [
    {
      "action": "resolve_recipient",
      "parameters": {
        "name": "Joel"
      }
    },
    {
      "action": "compose_email",
      "parameters": {}
    },
    {
      "action": "create_email_draft",
      "parameters": {}
    },
    {
      "action": "await_confirmation",
      "parameters": {}
    },
    {
      "action": "send_email",
      "parameters": {}
    }
  ]
}
```

The actual schema should be simple.

Don't add enormous numbers of fields.

---

# Phase 19 — Testing strategy changes

The current ~149 tests are valuable, but we need **workflow tests**, not only component tests.

We'll keep existing unit tests where they still represent valid behavior.

Add:

```text
1. simple conversation
2. information request
3. memory retrieval
4. email draft
5. missing recipient
6. missing subject
7. draft readback
8. modification
9. reconfirmation
10. cancellation
11. send success
12. send failure
13. pause
14. resume
15. task interruption
16. replanning
17. desktop executor simulation
```

Most important test:

```text
Executor fails
→ planner receives failure
→ task does not complete
→ Groq does not claim success
```

---

# Phase 20 — SQLite reliability

Only after orchestration stabilizes.

Then fix:

```text
database lock
```

with:

* explicit SQLite connection closure
* appropriate timeout
* WAL if justified
* correct shutdown ordering
* a concurrency/lock regression test

Don't mix this into the architecture work.

---

# Implementation order

This is the exact sequence I would use.

| Stage | Work                                | Result                         |
| ----- | ----------------------------------- | ------------------------------ |
| 1     | Gemini structured-output layer      | Reliable Intent/Plan JSON      |
| 2     | Clean `Task`/`Plan` model           | Single workflow state          |
| 3     | Multi-step Gemini Planner           | Real plans                     |
| 4     | One-step Executor loop              | Execute → result → planner     |
| 5     | Plan feedback/replanning            | Adaptive agent                 |
| 6     | Confirmation plan step              | Safe human boundary            |
| 7     | Groq generation layer               | Natural communication          |
| 8     | Gmail migration                     | Complete email workflow        |
| 9     | Modification/resume/interruption    | Focus 14 completed properly    |
| 10    | Information/conversation routing    | Non-task requests work cleanly |
| 11    | Desktop executor interface          | David's future work plugs in   |
| 12    | Remove old ConversationEngine hacks | Simpler architecture           |
| 13    | Full workflow regression            | Confidence                     |
| 14    | SQLite/session reliability          | Stable runtime                 |
| 15    | Live end-to-end testing             | Real ADVI validation           |

---

# What we should NOT do

This is just as important.

We will **not**:

```text
❌ rewrite the whole project
❌ create 10 new orchestration classes
❌ hard-code every natural-language phrase
❌ make Groq responsible for execution
❌ make Python hard-code the plan
❌ execute all planner steps blindly
❌ make every turn call both LLMs
❌ replace the existing Planner with a renamed duplicate
❌ throw away the existing TaskManager
❌ copy David's old project wholesale
```

David's code gives us one particularly useful pattern: **structured intent + structured multi-action plan**. His old planner explicitly generates complete action sequences, which is exactly the part our current planner is missing. 

But ADVI should go beyond that old implementation by making the plan **persistent, interruptible, re-plannable, and executable one step at a time**.

---

# The final mental model

This is the model I want us to code against:

```text
                         USER
                           │
                           ▼
                       INTENT
                       Gemini
                           │
                           ▼
                        PLAN
                       Gemini
                           │
                    complete steps
                           │
                           ▼
                    CURRENT STEP
                           │
                           ▼
                       EXECUTOR
                           │
               ┌───────────┼───────────┐
               ▼           ▼           ▼
            Python       Groq       Desktop
             Tool       Generate     Agent
               │           │           │
               └───────────┼───────────┘
                           ▼
                      RESULT / OBSERVATION
                           │
                           ▼
                        GEMINI
                           │
                  ┌────────┼────────┐
                  ▼        ▼        ▼
               NEXT      MODIFY    USER
               STEP       PLAN     INPUT
                  │
                  └───────────────►
```

And the core invariant is:

> **Plan everything, execute one step, report the result, re-evaluate, then execute the next step.**

That gives you the multi-step planner you wanted, the execution feedback loop you need for David's future desktop agent, the Gmail workflow you need now, and enough structure for Focus 14 without turning `conversation.py` into another 1,000-line control center.




