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





### Fix Plan (Focus 15):

# Final ADVI Architecture Plan

## 0. Freeze the working foundation

Keep these largely unchanged:

```text
Gmail API / OAuth
GmailService
LongTermMemory
MemoryRetriever
SessionBuffer / ShortTermMemory
Piper TTS
LLM provider abstraction
GeminiProvider
GroqProvider
Telemetry
Config / runtime
low-level Executor tool implementations
```

David's old project gives us the useful architectural principle: **Intent → structured Plan → Actions**, with explicit schemas rather than dozens of Python branches. 

---

# 1. New structured Intent

Replace the current enormous intent taxonomy with a compact structured model inspired by David's:

```text
goal
entities
constraints
missing_information
confirmation_required
```



Gemini's job:

> Understand what the user wants and what information is available/missing.

Example:

```json
{
  "goal": "send_email",
  "entities": {
    "recipient": "Joel",
    "body": "I won't be coming tomorrow because of the Eid holiday."
  },
  "constraints": [],
  "missing_information": [],
  "confirmation_required": true
}
```

**No execution logic here.**

---

# 2. New Planner

Replace the current one-step mapping.

David's planner already demonstrates the correct basic idea: produce a **complete sequence of actions** rather than one action. 

Our version goes further by making the plan resumable.

Example:

```text
Goal: send_email

1. resolve_recipient
2. compose_email
3. create_draft
4. readback
5. await_confirmation
6. send_draft
7. verify_send
```

The plan is **not executed all at once**.

---

# 3. Persistent Task/Plan state

Create one authoritative workflow state:

```text
Task
 ├── task_id
 ├── goal
 ├── plan
 ├── current_step
 ├── status
 └── context
```

Example:

```text
status = awaiting_confirmation

current_step = 5

context:
    recipient = Joel
    email = joel@example.com
    draft_id = abc123
    subject = ...
    body = ...
```

This becomes the memory of the workflow.

We stop duplicating execution state between `Plan` and `Task`.

---

# 4. AgentController / AgentLoop

This is the central new component.

Its job is simply:

```text
1. Give current state + user input to Gemini.
2. Gemini chooses the next action/decision.
3. Execute that action with Python.
4. Capture ExecutionResult.
5. Give the result back to Gemini.
6. Gemini chooses what happens next.
7. Repeat until waiting/completed/failed.
```

The core loop is:

```text
Gemini
   ↓
Action
   ↓
Python Executor
   ↓
ExecutionResult
   ↓
Gemini
   ↓
Next Action
   ↓
...
```

This directly solves the problem we currently have where Gemini classifies something and then Groq independently invents the rest.

---

# 5. Python becomes the execution authority

Python remains the only component allowed to say:

```text
Gmail draft created.
Gmail send succeeded.
File deleted.
Memory updated.
Action failed.
```

The Executor returns:

```text
ExecutionResult(
    action,
    success,
    data,
    error
)
```

No LLM can override this.

So:

```text
Executor says FAILED
→ system state = FAILED
→ Groq cannot say "completed"
```

This fixes the false-email-success bug at the architectural level.

---

# 6. Gemini ↔ Python feedback loop

Example:

```text
Gemini:
create_draft
```

Python:

```text
success
draft_id = 123
```

Send back to Gemini:

```text
Previous action:
create_draft

Result:
SUCCESS

Data:
draft_id=123
```

Gemini decides:

```text
next_action = await_confirmation
```

Then the task pauses.

Later:

```text
User:
"Make it more polite."
```

Gemini sees:

```text
current task
current draft
current step
new user request
```

and decides:

```text
modify_email_body
```

Python updates the existing draft.

Gemini receives the result and decides:

```text
return to await_confirmation
```

That's the behavior you were trying to achieve with Focus 14.

---

# 7. Confirmation becomes a plan state

Instead of a giant collection of special confirmation handlers:

```text
TASK_CONFIRMATION
TASK_REJECTION
EMAIL_SEND
...
```

the workflow reaches:

```text
await_confirmation
```

Task state:

```text
WAITING_FOR_USER
```

Then Gemini interprets the user's next message in context.

Examples:

```text
"yes"
→ continue

"send it"
→ continue

"make it more polite"
→ modify plan/current draft

"read it again"
→ readback

"cancel"
→ cancel

"pause this"
→ pause
```

The semantic interpretation remains LLM-driven.

The actual state transition remains deterministic.

That's the balance we wanted.

---

# 8. Groq's real role

Groq is **not merely TTS text generation**, but it also does not control execution.

Groq handles:

```text
natural-language conversation
email wording
readbacks
clarifying questions
confirmation wording
friendly explanations
final responses
```

For example:

```text
Gemini:
await_confirmation

↓

Groq:
"I've prepared the email to Joel. Here's the draft...
Would you like me to send it?"
```

User:

```text
"Actually, make it more polite."
```

Groq understands the natural-language interaction and passes the relevant conversational context into the agent flow.

Then Gemini decides how to modify the plan.

So the roles are:

```text
GEMINI = reasoning / planning / replanning

PYTHON = execution / truth / state

GROQ = language / conversation / presentation
```

---

# 9. Remove the current ConversationEngine special-case maze

Current `ConversationEngine` has accumulated separate handling for:

```text
pause
resume
readback
modification
confirmation
email continuation
memory
execution
final response
```

We will reduce it to:

```text
receive user input
        ↓
AgentController
        ↓
state/result
        ↓
Groq
        ↓
user response
```

ConversationEngine becomes an interface layer, not the brain of the agent.

---

# 10. Replace the current Planner

Current implementation is effectively:

```text
IntentType → one action
```

and only produces one `PlanStep`. 

Replace it with:

```text
Intent
 ↓
Gemini Planner
 ↓
ActionPlan
 ↓
steps[]
```

The planner can use the current task state when replanning.

---

# 11. Structured Gemini output

We already found two real failures:

````text
valid JSON wrapped in ```json fences
````

and:

```text
truncated JSON
```

So Gemini outputs must be handled at the provider/schema boundary.

Use:

```text
structured output
+
schema validation
+
defensive parsing
```

instead of letting `json.loads()` silently convert everything into `UNKNOWN`.

David's original implementation already uses Pydantic models for this separation. 

---

# 12. Shrink the intent prompt

The current prompt is doing too much.

The new model should not need dozens of categories to distinguish every possible task-control phrase.

It receives:

```text
current task
current plan
current step
user message
```

and interprets the message in context.

That should dramatically reduce the prompt size and hopefully the absurd 20–50 second classification latency we've been seeing.

We measure before/after rather than assume.

---

# 13. Handle missing information through the same loop

Example:

```text
User:
Send an email to David.

Gemini:
missing_information = recipient_email

Agent:
WAITING_FOR_USER

Groq:
"I don't have David's email address. What address should I use?"
```

User:

```text
david@example.com
```

Gemini receives current task + new information and resumes.

No `_resume_email_task()` special case.

---

# 14. Email workflow

The final email flow should be:

```text
User request
    ↓
Gemini intent
    ↓
Gemini plan
    ↓
resolve recipient
    ↓
compose email
    ↓
create Gmail draft
    ↓
readback
    ↓
WAITING_FOR_CONFIRMATION
    ↓
user modification?
    ├── yes → modify draft → readback → confirmation
    └── no
    ↓
send Gmail draft
    ↓
verify Gmail result
    ↓
COMPLETED
    ↓
Groq communicates verified outcome
```

That is the complete Focus 15 workflow.

---

# 15. Information requests become proper paths

For:

```text
"What is 2+2?"
```

Gemini should identify:

```text
goal = information_request
```

Then the system should not create a fake meaningless task and then secretly let Groq answer it.

Instead:

```text
information request
→ Groq / appropriate reasoning path
→ answer
```

No unnecessary task.

This fixes the current:

```text
information_request
→ Planner BLOCKED
→ Groq answers anyway
```

contradiction. 

---

# 16. Keep capability safety deterministic

These remain Python-controlled:

```text
Can this capability execute?
Is the tool available?
Is confirmation required?
Did execution succeed?
What exact result did the tool return?
```

LLMs do **not** decide these facts.

---

# 17. SQLite / session cleanup comes later

After the orchestration redesign works:

```text
explicit SQLite connection closing
WAL / timeout where appropriate
shutdown ordering
lock regression test
```

This stays separate from the agent redesign.

---

# 18. Testing strategy

We don't try to preserve every current test blindly.

We keep the useful unit tests, then add **workflow tests**.

Minimum end-to-end matrix:

```text
Conversation
Information request
Memory retrieval
Memory update
Email draft
Missing recipient
Email modification
Email confirmation
Email cancellation
Email send failure
Email send success
Pause
Resume
Task interruption
Task modification
Task completion
```

Most importantly:

```text
executor fails
→ final response MUST NOT claim success
```

---

# 19. Migration order

This is the order I would actually implement:

### Stage A — New models

```text
Intent
ActionPlan
PlanStep
TaskState
AgentDecision
ExecutionResult
```

Keep old code working.

### Stage B — New Gemini planner

Gemini produces structured plans.

### Stage C — AgentController

Implement:

```text
plan → execute → result → replan
```

with a fake executor first.

### Stage D — Connect existing Executor

Use real actions.

### Stage E — Connect Gmail

Migrate email to the new workflow.

### Stage F — Confirmation / modification

Implement pause-at-confirmation and mid-task replanning.

### Stage G — Groq integration

Use Groq to communicate the agent's authoritative state.

### Stage H — Migrate memory and other capabilities

Move them onto the same controller.

### Stage I — Remove old orchestration

Delete:

```text
ConversationEngine task hacks
email-specific continuation
duplicate confirmation paths
one-step planner
redundant state logic
```

### Stage J — SQLite cleanup + full regression

Then:

```text
pytest
integration tests
live Gmail test
```

---

# The final target

When this is finished, ADVI should behave like:

```text
                 USER
                   │
                   ▼
                GROQ
           understand/talk
                   │
                   ▼
               GEMINI
          plan / reason / revise
                   │
                   ▼
               PYTHON
         execute exact action
                   │
                   ▼
           ExecutionResult
                   │
                   └──────────────┐
                                  ▼
                               GEMINI
                          decide next step
                                  │
                  ┌───────────────┼───────────────┐
                  ▼               ▼               ▼
               execute        ask user          finish
                  │               │               │
                  └───────────────┘               ▼
                                              GROQ
                                                │
                                                ▼
                                               USER
```



