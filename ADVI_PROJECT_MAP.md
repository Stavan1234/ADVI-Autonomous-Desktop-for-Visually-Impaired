# ADVI Project Map

> **Generated:** 2026-09-15  
> **Purpose:** AI-readable architecture and codebase map for future development agents (especially Antigravity).  
> **Project:** ADVI — Autonomous Desktop for Visually Impaired

## 0. How to use this document

This file is a **map, not a specification**. It describes the two repository snapshots supplied for the current merge/rebuild effort, what each major part currently does, how they connect, and where the important implementation boundaries are.

### Source-of-truth rule

1. **Actual source code is the final source of truth.**
2. This document is a navigation aid and architectural summary.
3. The attached engineering PDFs are useful historical/design records; they describe why many decisions were made, but they can lag the code snapshot. Do not assume a PDF description is still identical to the current implementation without checking source.
4. When this repository changes, update this file so another AI agent can quickly re-enter the project.

## 0.1 Unified ADVI Architecture (Completed Implementation)

The rebuild and unification of ADVI into **one coherent AI computer agent** is implemented. David's desktop automation machinery and Chrome CDP browser control have been promoted from isolated "fallback" scripts into ADVI's primary, modular capability layer.

### High-Level Feedback Cycle

```text
User
  ↓
ADVI Brain (`ADVIAgent` in `src/advi/brain/agent.py`)
  ↓
Context Assembly (`AgentContext` in `src/advi/brain/context.py`):
  - Recent conversation (ShortTermMemory)
  - Retrieved user facts (LongTermMemory / MemoryRetriever)
  - Active task / workflow context (`ActiveTask` in `src/advi/brain/task_state.py`)
  - Authoritative capability summary (`CapabilityRegistry`)
  - ADVI persona and principles
  ↓
Cognitive Decision:
  ├─ Conversation path: direct natural dialogue response (zero overhead)
  ├─ Memory path: store or retrieve user facts with grounded answer
  └─ Action/Workflow path:
       ↓
     Action Plan (`ActionPlan` in `src/advi/core/action_plan.py`)
       ↓
     Execution Engine (`ExecutionEngine` in `src/advi/core/execution_engine.py`)
       ↓
     Modular Capabilities (`src/advi/capabilities/`):
       ├─ Desktop (`DesktopCapability`): apps, window focus, typing, keys, mouse, UIA/vision perception
       ├─ Browser (`BrowserCapability`): Chrome CDP client, tab navigation, in-page search, clicks
       ├─ Files (`FileCapability`): file creation/reading, Desktop path resolution
       ├─ Gmail (`GmailCapability`): draft, search, read, send email
       └─ Memory (`MemoryCapability`): facts persistence, semantic search, forgetting
       ↓
     Generalized Verification (`ActionVerifier` in `src/advi/core/verification.py`):
       - Checks file existence & size on disk
       - Confirms window HWND and foreground focus
       - Verifies browser URL matching & email message IDs
       ↓
     Standardized Result (`ExecutionResult` in `src/advi/core/action_plan.py`)
       ↓
     Context update in Brain
       ↓
Natural, truthful grounded response to user (speech via PiperTTS + text console)
```

### Production Entry Point

- `src/advi/app.py` (`advi = advi.app:main`): One unified production CLI entry point initializing `Runtime`, `CapabilityRegistry`, `ExecutionEngine`, `ADVIAgent`, and `OutputManager`.

---

### Supplied snapshots

- **Primary/current ADVI snapshot:** `codebase_advi_1.zip` — extracted as `/mnt/data/advi_latest` during generation; source tree is under `src/advi`.
- **David snapshot:** `ADVI-Autonomous-Desktop-for-Visually-Impaired-v2-main(1).zip` — extracted as `/mnt/data/advi_david/ADVI-Autonomous-Desktop-for-Visually-Impaired-v2-main` during generation.
- **Engineering/design records:** three memory/architecture PDFs plus two intent/planner PDFs supplied in the conversation. They document earlier focuses and implementation lessons.

---

# 1. ADVI product definition

ADVI stands for **Autonomous Desktop for Visually Impaired**. The long-term product is a voice-oriented AI desktop assistant that understands natural language, maintains useful context, remembers persistent information, interacts with computer resources, works with files and services, and eventually performs multi-step autonomous desktop actions.

The engineering documentation explicitly emphasizes: correct behavior, fast interaction, reliability, contextual intelligence, low unnecessary complexity, reasonable API/token usage, and maintainability. The memory architecture settled on a local SQLite-centered approach supplemented by FTS, local embeddings, relationships, sessions, and LLM reasoning. The design rationale is that a desktop assistant benefits from local persistence, lower latency, and simpler deployment. [Source: ADVI Technical Documentation — Part 1 of 3, “Development Philosophy”]

The strongest documented architectural principle is:

> The LLM provides intelligence and natural communication; deterministic local components provide structure, state, validation, memory access, and execution control. [Source: ADVI Engineering Milestone Report — Part 1, Overview]

A second critical principle came from memory failures: local retrieval should supply **evidence/context**, not independently author the final user-facing answer. The final LLM should reason over retrieved evidence and communicate the answer. [Source: ADVI Engineering Milestone Report — Part 1, memory retrieval architecture]

---

# 2. Current strategic direction

The intended rebuild should not preserve complexity merely because it exists. The final system may consolidate, replace, move, or delete components when that makes ADVI simpler and more coherent.

The desired runtime shape is approximately:

```text
User
  ↓
ADVI Brain / Context
  ↓
Understand + Reason + Decide
  ↓
Tool / Capability selection
  ↓
Action plan or direct tool call
  ↓
Real execution
  ↓
Actual result / observation
  ↓
Verification
  ↓
Result returned to context
  ↓
LLM continues or responds
```

The LLM must not fabricate execution success. Actual file, GUI, browser, Gmail, or application operations must be performed by executable software and return concrete results.

---

# 3. Repository comparison at a glance

The two repositories overlap heavily.

- Primary snapshot has the richer developed **core conversation/task/memory/Gmail/intelligence** implementation.
- David's snapshot contains a broadly similar core foundation but additionally contains a substantial, relatively self-contained **fallback desktop-agent stack**.
- David's repository also contains `fallback-old/`, which is a duplicated historical fallback implementation and should not automatically be carried forward.
- David's `fallback/` is the important subsystem to study/merge.
- The primary snapshot, as supplied, does **not** include a `pyproject.toml` or root `requirements.txt`; it does contain generated/setuptools metadata under `src/advi_desktop_agent.egg-info/`.
- David's snapshot includes `pyproject.toml`, `requirements.txt`, `.env.example`, bundled Piper assets, and explicit CLI entry-point configuration.

### Common source files

Both snapshots contain 40 matching paths under `src/advi`; only 10 are byte-identical. 30 common paths differ in implementation.

**Byte-identical common files:**

- `__init__.py`
- `brain/__init__.py`
- `core/config.py`
- `io/__init__.py`
- `io/console.py`
- `io/tts.py`
- `memory/__init__.py`
- `personality/__init__.py`
- `providers/__init__.py`
- `tools/__init__.py`

**Common but implementation-different files:**

- `app.py`
- `core/capabilities.py`
- `core/conversation.py`
- `core/executor.py`
- `core/intent.py`
- `core/intent_detector.py`
- `core/intent_handler.py`
- `core/llm_telemetry.py`
- `core/local_responses.py`
- `core/logging.py`
- `core/memory_context.py`
- `core/memory_resolver.py`
- `core/personality.py`
- `core/planner.py`
- `core/response_policy.py`
- `core/runtime.py`
- `core/task.py`
- `core/task_coordinator.py`
- `core/task_manager.py`
- `io/dev_display.py`
- `io/output.py`
- `memory/consolidator.py`
- `memory/long_term.py`
- `memory/retriever.py`
- `memory/session.py`
- `memory/short_term.py`
- `providers/base.py`
- `providers/errors.py`
- `providers/gemini.py`
- `providers/groq.py`

This is important: David's repository is not simply "your repository plus fallback". Many shared core files differ, often substantially.

---

# 4. Runtime and packaging

## Primary/current snapshot

### Entry point evidence

`src/advi_desktop_agent.egg-info/entry_points.txt` declares:

```text
[console_scripts]
advi = advi.app:main
```

However, the supplied snapshot has no root `pyproject.toml`, so packaging metadata is present but the source archive itself is incomplete as a clean rebuildable distribution.

### `src/advi/app.py`

Current primary startup constructs the following chain:

```text
Runtime
 ↓
PiperTTS / OutputManager
 ↓
GroqProvider
 ↓
(optional) GeminiProvider
 ↓
LLM telemetry
 ↓
IntentDetector
 ↓
MemoryRetriever
 ↓
MemoryResolver
 ↓
IntentHandler
 ↓
Planner
 ↓
Executor
 ↓
TaskCoordinator
 ↓
ConversationEngine
 ↓
SessionConsolidator
```

The main loop reads console input, sends it to `ConversationEngine.respond()`, delivers the response through `OutputManager`, and on shutdown performs session consolidation and runtime shutdown.

### David snapshot packaging

David's `pyproject.toml` declares:

- Python `>=3.13,<3.14`
- `groq`
- `python-dotenv`
- `requests`
- Google auth / Gmail libraries
- DNS support
- sounddevice / soundfile
- watchdog
- pypdf
- python-docx
- pywinauto
- sentence-transformers
- numpy
- pyautogui
- pytest as a development dependency

The CLI entry point is also `advi = advi.app:main`.

David bundles Piper binaries/models and includes a standalone fallback test runner.

---

# 5. Primary repository — directory map

```text
src/advi/
├── __init__.py
├── app.py
├── brain/
│   └── __init__.py
├── core/
│   ├── capabilities.py
│   ├── config.py
│   ├── conversation.py
│   ├── executor.py
│   ├── intent.py
│   ├── intent_detector.py
│   ├── intent_handler.py
│   ├── llm_telemetry.py
│   ├── local_responses.py
│   ├── logging.py
│   ├── memory_context.py
│   ├── memory_resolver.py
│   ├── personality.py
│   ├── pipeline_trace.py
│   ├── planner.py
│   ├── response_policy.py
│   ├── runtime.py
│   ├── task.py
│   ├── task_coordinator.py
│   └── task_manager.py
├── integrations/
│   └── gmail/
│       ├── __init__.py
│       ├── auth.py
│       ├── models.py
│       └── service.py
├── io/
│   ├── __init__.py
│   ├── console.py
│   ├── dev_display.py
│   ├── output.py
│   └── tts.py
├── memory/
│   ├── __init__.py
│   ├── consolidator.py
│   ├── long_term.py
│   ├── retriever.py
│   ├── session.py
│   └── short_term.py
├── personality/
│   └── __init__.py
├── providers/
│   ├── __init__.py
│   ├── base.py
│   ├── errors.py
│   ├── gemini.py
│   ├── gemini_trace.py
│   └── groq.py
└── tools/
    └── __init__.py
```

---

# 6. Primary core — detailed responsibilities

## `core/config.py`

Defines configuration paths and environment settings.

Important constants:

```text
PROJECT_ROOT
ASSET_ROOT
RUNTIME_ROOT
LOG_ROOT
MEMORY_ROOT
MEMORY_DATABASE
```

`Settings` contains:

- `groq_api_key`
- `gemini_api_key`
- `groq_model`
- `gemini_model`
- `piper_exe`
- `piper_model`
- `tts_output`

`load_settings()` loads `.env` from `PROJECT_ROOT` and uses defaults such as `openai/gpt-oss-120b` for Groq and `gemini-3.6-flash` for Gemini in the supplied snapshot.

## `core/runtime.py`

`Runtime` owns startup/shutdown concerns:

- load settings
- configure logging
- create runtime/memory/audio directories
- report provider availability
- track `started`

The documented memory lifecycle is approximately: create runtime → start persistent memory → start session → conversation → session consolidation → end session/shutdown. [Source: ADVI Technical Documentation — Part 2 of 3, Core Runtime Lifecycle]

## `core/capabilities.py`

Implements a lightweight capability registry with:

- `CapabilityStatus`: available / partial / unavailable
- `Capability`: name, description, status
- `CAPABILITIES` registry
- lookup helpers
- compact capability summaries
- `capability_for_prompt()` for model context

This is the self-model foundation: LLM knowledge must not be confused with actual connected ADVI capability. The documented architecture explicitly feeds real capability state into model context. [Source: ADVI Engineering Milestone Report — Part 1, Focus 8]

## `core/personality.py`

Defines ADVI identity/principles/communication policy and exposes `build_advi_system_prompt()`.

The documented identity decision is to provide ADVI identity explicitly as system context rather than expecting the model to infer its identity from prior conversation. This keeps identity stable across sessions, memory retrieval and provider changes. [Source: ADVI Engineering Milestone Report — Part 1, Focus 7]

## `core/response_policy.py`

Small local response-style layer:

- `detect_response_mode(user_input)`
- `build_response_policy(user_input)`

It supports concise/default behavior and recognizes requests for more detail or brevity.

---

# 7. Primary intent system

## `core/intent.py`

Defines:

- `IntentType` enum
- immutable `Intent` dataclass
- post-init validation/clamping behavior

Documented intent categories include:

```text
conversation
memory_retrieval
memory_update
memory_forget
capability_query
identity_query
information_request
system_control
unknown
```

The structured intent model was designed to capture type, confidence, original input, target, entities and parameters. [Source: ADVI Engineering Milestone Report — Part 1, Focus 9]

## `core/intent_detector.py`

`IntentDetector` calls an LLM and parses structured JSON into the core `Intent` object.

Important methods:

- `__init__(provider, telemetry)`
- `_build_task_context()`
- `set_current_task(task)`
- `detect(user_input)`
- `_parse(text, original_input)`

The detector has current-task awareness and therefore participates in multi-turn task interpretation.

### Known historical debugging note

A recent failure in one development snapshot occurred before `IntentDetector.ENTER`: `_build_task_context()` accessed `step.parameters` on `TaskStepState`, while that state object had fields such as `action`, `status`, `result`, and `error` but not `parameters`. This is a concrete example of why current code should be treated as authoritative and why task-schema changes must be synchronized with intent context building.

## `core/intent_handler.py`

Bridges intent and memory mutation/decision logic.

Responsibilities include:

- handling structured intent
- applying memory decisions
- forgetting memory when appropriate

## `core/memory_resolver.py`

Defines:

- `MemoryOperation`
- `MemoryDecision`
- `MemoryResolver`

The resolver asks an LLM for structured memory mutation intent (create/update/forget/ignore style operations), validates the result, and applies only permitted memory mutations through local storage/handlers.

---

# 8. Primary planning system

## `core/planner.py`

Defines:

- `PlanStatus`
- `PlanStep`
- `Plan`
- `Planner`

Important methods:

- `create_plan()`
- `decide_next_step()`
- `_parse_next_step()`
- `_llm_plan()`
- `_parse_plan()`
- `_fallback_plan()`

The primary planner snapshot is significantly larger than David's corresponding `core/planner.py` and represents a more developed deterministic/LLM hybrid planning path.

Documented design direction: simple known tasks can remain deterministic, while complex multi-step tasks are a natural candidate for an LLM planner. [Source: ADVI Engineering Milestone Report — Part 2, Hybrid Planner direction]

## Important distinction from David fallback planner

Primary `core.planner.py` produces the project's internal `Plan/PlanStep` representation.

David's `fallback/planner_service.py` produces a desktop-specific `ActionPlan` containing concrete desktop/browser action objects.

These are not the same contract and should not be merged blindly.

---

# 9. Primary execution/task state

## `core/task.py`

Defines task state models:

- `TaskStatus`
- `TaskStepStatus`
- `ConfirmationStatus`
- `ConfirmationRequest`
- `TaskStepState`
- `Task`

The supplied snapshot contains duplicate `TaskStatus` declarations in this file; this should be reviewed during rebuild rather than assumed intentional.

## `core/task_manager.py`

The TaskManager is a substantial state-management component.

Capabilities include:

```text
create
update_context
get_context
current_task
pause_current
resume_last_paused
paused_tasks
invalidate_confirmation
get
start
pause
resume
await_input
await_confirmation
approve
reject
append_step
start_step
complete_step
fail_step
cancel
```

It tracks task lifecycle and step transitions rather than executing the action itself.

## `core/task_coordinator.py`

`TaskCoordinator` connects planning and execution and adds task-level semantics.

Responsibilities include:

- current task access
- task-intent handling
- pause/resume
- email-recipient normalization and resolution
- task modification
- task context/readback
- running an execution

Important methods:

```text
handle_task_intent
pause_current_task
resume_last_paused_task
modify_current_task
get_current_task_context
readback_current_task
resolve_email_recipient
missing_email_recipient
run
```

The architecture currently has a relatively large amount of orchestration here. During rebuild, evaluate whether all of it remains necessary.

---

# 10. Primary executor

## `core/executor.py`

Defines:

- `ExecutionResult`
- `Executor`

Current executor is **not** a general desktop automation engine. It focuses on internal ADVI actions such as:

```text
memory retrieval
memory update
memory forget
capability query
identity query
conversation
email draft creation
email draft reading
email draft updates
email sending
```

This is one of the biggest architectural differences between the primary core and David's fallback executor.

The primary executor acts as an application-level action executor.

David's fallback executor acts as a real Windows/browser automation executor.

---

# 11. Primary conversation engine

## `core/conversation.py`

`ConversationEngine` is currently one of the largest files in the primary snapshot (~1618 lines).

Key methods:

- `respond(user_input)`
- `_compose_email_draft(intent)`
- `_resume_email_task(task, email_address)`
- `_format_memory_operation_context(intent, result)`
- `get_session_buffer()`

Responsibilities currently include much more than ordinary conversation:

```text
short-term conversation
memory retrieval context
previous session context
personality/capability context
intent detection
memory operations
planning
task coordination
email workflows
LLM final response generation
telemetry/tracing
developer display
```

The documented conversation architecture sends the current conversation plus bounded relevant long-term memories, relationships, and recent session context to the model. [Source: ADVI Technical Documentation — Part 1 of 3, Conversation Engine]

This is powerful but also one of the first places to inspect when simplifying the architecture.

---

# 12. Primary memory architecture

The memory system is SQLite-centered and was deliberately designed to avoid heavier graph/database infrastructure. The documentation explicitly states that SQLite is the persistent foundation, with graph-like behavior implemented only as needed. fileciteturn60file2L44-L63

## `memory/short_term.py`

`ShortTermMemory` holds bounded recent conversation.

Methods:

- `add`
- `_trim`
- `get_messages`
- `remove_last`
- `clear`
- `count`

The design intentionally bounds short-term context so prompt size, latency and token usage do not grow forever. Evicted messages go to a session buffer instead of disappearing immediately. [Source: ADVI Technical Documentation — Part 1 of 3, Short-Term Memory and Session Buffer]

## `memory/session.py`

`SessionBuffer` stages messages evicted from short-term memory.

Methods:

- `add`
- `drain`
- `count`
- `clear`

## `memory/long_term.py`

`LongTermMemory` is the persistent SQLite layer.

Models:

- `Relationship`
- `Memory`
- `MemoryHistory`
- `Contact`

Major methods:

```text
_connect
_initialize
all
remember
history
normalize_email
extract_email
get_contact
save_contact
recent_sessions
recall
search
forget
clear
start_session
end_session
remember_relationship
find_relationships
search_relationships
related_entities
save_consolidation
latest_session
```

The database path is configured as `runtime/memory/advi_memory.db` in the documented architecture. A session is a container for a period of interaction; durable memory is information extracted from that interaction that should survive it. fileciteturn60file3L28-L50

## `memory/retriever.py`

Hybrid retrieval using:

- local embeddings via SentenceTransformer
- SQLite FTS lexical retrieval

`MemoryRetriever` lazy-loads the embedding model only when semantic search is first required.

The documented hybrid score is approximately:

```text
0.85 × semantic_score + 0.15 × lexical_score
```

FTS is stronger at names/keys/distinctive terms; embeddings are stronger at paraphrases. The retrieval system intentionally returns a candidate pool for the LLM to reason over instead of asserting that top similarity equals truth. [Source: ADVI Technical Documentation — Part 2 of 3, Hybrid Score]

## `memory/consolidator.py`

Defines:

- `MemoryCandidate`
- `RelationshipCandidate`
- `ConsolidationResult`
- `SessionConsolidator`

It turns session material into candidate durable memories/relationships and a session summary.

## `core/memory_context.py`

`MemoryContextBuilder.build()` assembles memory context for the reasoning/response path.

---

# 13. Memory lessons that must survive the rebuild

These are especially valuable for any future agent because they came from real failures.

### Retrieval is not the same as reasoning

A semantic retriever can return a strongly related but wrong personal fact. The documented correction was to use local retrieval to produce evidence and let the final LLM reason over that evidence. fileciteturn60file0L172-L210

### Retrieve enough candidates

The candidate pool was increased from overly strict top-N selection because narrow retrieval could omit the correct fact. The final LLM is better positioned to choose among a bounded set of plausible candidates. [Source: ADVI Technical Documentation — Part 2 of 3, Long-Term Memory Retrieval]

### FTS must actually contain current rows

One real incident had the expected memory rows in SQLite but the FTS search returning nothing because the index needed rebuilding. The repair used SQLite FTS rebuild. [Source: ADVI Technical Documentation — Part 3 of 3, FTS Debugging]

### Natural language needs lexical normalization

Possessives such as `father's` caused undesirable FTS behavior and were normalized before FTS query construction. [Source: ADVI Technical Documentation — Part 3 of 3, FTS Possessive Normalization]

### Do not import heavyweight infrastructure unnecessarily

An earlier indirect Cognee import added roughly 15.6 seconds of import-time latency; removing it from the hot import path plus lazy model initialization reduced that path to roughly 0.68 seconds in the documented test. [Source: ADVI Technical Documentation — Part 3 of 3, Cognee Import Latency]

---

# 14. Providers

## `providers/base.py`

Defines the provider abstraction and normalized `LLMResponse`.

The normalized response includes provider/model usage and timing fields used by telemetry.

## `providers/groq.py`

`GroqProvider` implements the LLM provider abstraction for Groq.

## `providers/gemini.py`

`GeminiProvider` implements Gemini integration.

The documented division of responsibility was:

```text
Gemini → internal structured intelligence
Groq   → final user-facing conversational generation
```

The provider layer was intentionally normalized so the rest of ADVI does not have to depend on vendor-specific response shapes. [Source: ADVI Engineering Milestone Report — Part 2, Dual LLM Provider Architecture]

## `providers/errors.py`

Defines normalized error types:

- `LLMError`
- `LLMAuthenticationError`
- `LLMRateLimitError`
- `LLMTimeoutError`
- `LLMUnavailableError`
- `LLMResponseError`

## `providers/gemini_trace.py`

Converts Gemini-native response/config/content structures into trace-friendly dictionaries.

---

# 15. Observability and debugging

## `core/llm_telemetry.py`

Defines:

- `LLMCallRecord`
- `LLMTelemetry`

Tracks:

- provider
- model
- purpose
- latency
- input tokens
- output tokens
- total tokens
- request-level call history

The documented goal is lightweight in-memory telemetry, not a monitoring database. It exists to answer: which model ran, why it ran, how long it took, how many tokens were used, and how many calls one request required. fileciteturn60file1L7-L19

## `core/pipeline_trace.py`

Provides structured turn/task/LLM tracing helpers, serialization helpers for intents/plans/tasks/execution results/LLM responses, summaries, boundaries, and exception tracing.

## `core/logging.py`

Configures logging and defines `AdviFormatter`.

### Known debugging limitation from the development history

At one point `logger.exception(...)` technically captured tracebacks, but the custom formatter rendered only `record.getMessage()`, so the traceback did not appear in console logs. This matters when changing logging: make sure exception traces remain inspectable.

## `io/dev_display.py`

Formats developer-readable sections such as:

```text
INTENT
PLAN
TASK
LLM SUMMARY
```

This is distinct from the user-facing response.

---

# 16. I/O

## `io/console.py`

- `print_banner()`
- `read_line()`
- `print_shutdown()`

The current primary banner still says the foundation runtime is online and intelligence modules are not enabled yet, even though substantial intelligence code exists. This is an example of stale presentation text that should be corrected during rebuild.

## `io/output.py`

Defines:

- `AdviResponse`
- `OutputManager`

A response has separate display and speech representations. Markdown is simplified for speech; tables become spoken row-like descriptions; code blocks and raw URLs are removed/cleaned.

## `io/tts.py`

Piper TTS support:

- `clean_for_speech`
- `play_wav`
- `PiperTTS.available`
- `PiperTTS.synthesize`
- `PiperTTS.speak`

Piper is optional based on executable/model availability.

---

# 17. Gmail integration

`integrations/gmail/` contains:

- `auth.py`
- `models.py`
- `service.py`

## `GmailService`

Methods:

```text
search_messages
search_parsed_messages
get_message
get_parsed_message
_extract_body
_decode_body
create_draft
get_draft
update_draft
send_draft
```

Models:

- `GmailMessage`
- `GmailDraft`

The current conversation/executor path can compose a draft with Groq, keep the Python/Gmail layer authoritative for recipient identity and execution, update/read drafts, and send the draft.

This is already significantly more mature than a bare API wrapper because the surrounding task system handles recipient resolution and draft/task continuity.

---

# 18. David's fallback architecture

David's most valuable contribution is the separate desktop-agent subsystem under:

```text
src/advi/fallback/
```

It currently contains approximately 5,350 lines across the main fallback Python files.

The core flow is:

```text
User input
 ↓
IntentService
 ↓
Intent
 ↓
PlannerService
 ↓
ActionPlan
 ↓
ExecutionLoop
 ↓
ScreenPerception / Vision / CDP where needed
 ↓
FallbackExecutor
 ↓
Real Windows/browser
```

This is fundamentally different from the primary executor, which is mostly about ADVI-level logical actions such as memory and Gmail.

---

# 19. David fallback — schemas

## `fallback/intent_schema.py`

Pydantic `Intent`:

```python
goal: str = ""
entities: dict[str, Any]
constraints: list[str]
confirmation_required: bool = False
missing_information: list[str]
```

This is intentionally much broader and simpler than the primary `core.Intent` model. It is oriented toward an agentic desktop request rather than ADVI's internal conversational intent taxonomy.

## `fallback/action_plan_schema.py`

Pydantic models:

```python
class Action:
    action: str
    focus: str | None
    parameters: dict[str, Any]

class ActionPlan:
    actions: list[Action]
```

The `parameters` dictionary holds semantic action details such as targets, queries, URLs, application names, file names, etc.

---

# 20. David fallback — IntentService

## `fallback/intent_service.py`

Responsibilities:

- load `prompts/intent_prompt.txt`
- build a request around user input
- call an LLM through the common `LLMProvider` abstraction
- parse JSON
- instantiate the fallback Pydantic Intent

The system prompt tells the model it is ADVI's agentic desktop intent extraction component and requests valid JSON only.

Important current limitation: this service itself is essentially one-shot. It does not intrinsically own the primary ADVI conversation memory/task system.

---

# 21. David fallback — PlannerService

## `fallback/planner_service.py`

This is a major component (~1,160 lines).

The LLM decides:

- ordered action sequence
- semantic parameters
- semantic UI targets

Deterministic validation then checks/repairs the generated plan.

### Supported action types

The current `SUPPORTED_ACTIONS` set includes:

```text
open_application
focus_window
click
double_click
right_click
type_text
press_key
hotkey
select_file
attach_file
wait
scroll
search
navigate
submit
close_window
finish
```

### Important planner principle

The planner is deliberately **not** responsible for website-specific grounding. It can say `target="YouTube search box"` or `target="Save button"`; the perception/execution layers determine how that target maps to an actual UI element.

### Focus semantics

The planner uses `focus` separately from semantic targets.

For Chrome, the prompt explicitly insists on `focus="Chrome"` for Chrome actions rather than inventing tab/window implementation identifiers. The executor maintains logical Chrome-tab ownership.

This separation is a strong design idea worth preserving.

---

# 22. David fallback — ExecutionContext

`fallback/execution_context.py` holds execution-scoped state across a single automation plan.

Fields include:

```text
current_application
target_hwnd
chrome_cdp_port
chrome_process_id
chrome_window_hwnd
target_tab_id
target_tab_url
target_tab_title
metadata
```

Important behaviors:

- reset between distinct tasks
- maintain target Chrome tab identity
- maintain target Chrome window handle
- separate logical target ownership from OS focus
- track current application

This is an important execution-level state object and should not automatically be confused with ADVI's conversational `Task` state.

---

# 23. David fallback — ExecutionLoop

`fallback/execution_loop.py` owns the ordered action execution loop.

It:

1. maintains an `ExecutionContext`
2. iterates through planned actions
3. resolves semantic targets through `ScreenPerception` where needed
4. delegates concrete operations to `FallbackExecutor`
5. stops on failure
6. collects action results
7. returns `ExecutionLoopResult`

`ExecutionLoopResult` captures success/results/metadata for the automation run.

This is the closest thing in the supplied codebase to the desired:

```text
plan → execute → observe concrete result
```

foundation.

---

# 24. David fallback — FallbackExecutor

`fallback/executor.py` is the main real-computer execution layer (~757 lines).

It uses Windows/desktop/browser mechanisms such as:

- `pyautogui`
- Windows process/window APIs via `ctypes`
- subprocess application launch
- HTTP/WebSocket-style CDP interactions through `CDPBrowser`
- OS focus management

Supported behavior includes:

```text
open_application
focus_window
close_window
wait
click
double_click
right_click
type_text
press_key
hotkey
search
navigate
scroll
finish
```

It has special behavior for Chrome, including starting/finding Chrome, maintaining task-owned browser/tab context, activating a target tab, and avoiding unrelated open tabs.

This is the primary reason David's fallback is valuable to the merge: it is actual computer control rather than merely logical ADVI action execution.

---

# 25. David fallback — Perception

`fallback/perception.py` is a large semantic UI grounding layer (~1,235 lines).

`ScreenPerception` resolves natural-language targets to concrete desktop controls.

### Resolution approach

The documented class design prefers:

```text
1. Windows UI Automation
2. Vision fallback
```

For search fields, it is intentionally cautious because a browser address bar is also an editable control. Generic `Edit` controls are not automatically accepted as website search fields.

This is a valuable separation:

```text
Planner:
"click the YouTube search box"

Perception:
"which actual control is the YouTube search box?"

Executor:
"perform the click"
```

---

# 26. David fallback — Vision

`fallback/vision.py` (~1,056 lines) provides screen capture and visual target resolution helpers.

It uses `pyautogui` plus Windows/UIA helpers and can:

- capture screen
- locate relevant window
- find search targets
- find generic targets
- infer application hints
- normalize semantic text
- parse confidence information

This gives the fallback a second grounding path when pure UI Automation is insufficient.

---

# 27. David fallback — CDP Browser

`fallback/cdp_browser.py` (~620 lines) is responsible for Chrome DevTools Protocol interactions.

It handles browser-level operations such as:

- connect/list tabs
- send CDP commands
- activate tabs
- inspect/track tab context
- browser navigation/search support

The important architectural idea is that browser actions do not have to be implemented as blind mouse/keyboard automation when a browser-native protocol is more reliable.

---

# 28. David fallback — Router

`fallback/router.py` defines:

- `RouteResult`
- `FallbackRouter`

Current hard-coded fallback goals include:

```text
open_application
send_email
search_web
play_music
create_document
shutdown_system
```

The router currently recognizes a limited list of goal strings. It is therefore a **routing prototype**, not a complete general routing architecture.

It should be reconsidered during the merge rather than blindly retained.

---

# 29. David fallback — FallbackService

`fallback/service.py` wraps:

```text
IntentService
PlannerService
ExecutionLoop
```

It performs one high-level processing cycle:

```text
user input
 ↓
intent
 ↓
missing-info / confirmation check
 ↓
plan
 ↓
execution
```

Important limitation: `FallbackService.process()` does not itself maintain full multi-turn ADVI conversation state, memory, or the primary task system.

David's standalone `test_fallback_full.py` works around this by maintaining a local conversation list and repeatedly asking the fallback IntentService to reinterpret the accumulated text when the user supplies missing information or confirmation.

This is useful evidence of the fallback's capability, but it should not automatically become the final ADVI conversation architecture.

---

# 30. David fallback — prompts

Important files:

```text
fallback/prompts/intent_prompt.txt
fallback/prompts/planner_prompt.txt
```

These prompts contain substantial desktop-agent behavior rules around:

- semantic action extraction
- missing information
- confirmation
- action sequencing
- application focus
- browser/Chrome semantics
- search targets
- keyboard normalization
- outcome-based planning
- semantic UI targets

They should be treated as implementation assets worth studying, not as immutable architecture.

---

# 31. David `fallback-old/`

David's repository also contains:

```text
src/advi/fallback-old/
```

It duplicates the conceptual fallback stack:

```text
intent schema/service
planner service
action plan schema
execution loop
executor
router
service
perception
vision
prompts
```

Do not carry both implementations into a new final architecture without a concrete reason. `fallback-old` should be regarded as historical/reference material unless inspection proves a unique needed feature absent from current `fallback/`.

---

# 32. Standalone fallback test harnesses

## `test_fallback_full.py`

This script is the clearest evidence of the fallback's intended usage.

It imports:

```text
ExecutionLoop
IntentService
PlannerService
GroqProvider
```

It manually creates a Groq provider, points IntentService/PlannerService at the fallback prompt files, asks for one user request, and maintains a small local conversation list while resolving missing information/confirmation before planning/executing.

The script hardcodes its model to:

```text
openai/gpt-oss-safeguard-20b
```

in the supplied David snapshot.

## `test_fallback_suite.py`

Contains suite-style hard-coded action-plan cases covering desktop/browser scenarios. These tests are useful as behavioral references, but they are not equivalent to full autonomous end-to-end evaluation.

---

# 33. Critical runtime fact: `advi` is not currently the fallback

David's repository still has `advi = advi.app:main`, and `src/advi/app.py` imports/constructs the old core pipeline. A static inspection of `app.py` found no direct import/use of `FallbackService`, `FallbackRouter`, or the current fallback stack.

Therefore:

```text
python test_fallback_full.py
```

and:

```text
advi
```

are currently **different execution paths**.

The first explicitly runs the fallback. The second still launches the main core architecture.

This is a key merge detail.

---

# 34. Where the two systems fundamentally differ

| Concern | Primary/current ADVI | David fallback |
|---|---|---|
| Conversation | Strong, central `ConversationEngine` | Minimal/one-shot wrapper |
| Long-term memory | SQLite + FTS + embeddings + relations | Not a primary fallback concern |
| Short-term memory | Explicit bounded buffer | Local conversation list only in test harness |
| Identity/personality | Explicit system prompt | Not central to fallback |
| Intent | ADVI intent taxonomy | Desktop-agent goal/entity schema |
| Planning | Internal `Plan/PlanStep` | Desktop `ActionPlan/Action` |
| Task state | Rich task manager/coordinator | Execution-scoped context |
| Logical execution | Memory/Gmail/etc. | Real Windows/browser actions |
| GUI perception | Not primary executor concern | UIA + vision |
| Browser | Not primary executor concern | CDP + UI automation |
| Gmail | Real Gmail integration | Not the primary fallback capability |
| Verification | Limited/needs expansion | Concrete action results, but full semantic verification is still future work |
| Routing | Primary pipeline orchestration | Limited fallback router |
| Telemetry | Rich in-memory call/trace infrastructure | Basic logging |

This is why the best merge is not "pick one repository and discard the other." The repositories provide **different strengths**.

---

# 35. Recommended conceptual final architecture

A clean eventual design can be organized around a small number of responsibilities.

```text
                         ┌──────────────────────┐
                         │        ADVI          │
                         │ Conversation + Brain │
                         └──────────┬───────────┘
                                    │
               ┌────────────────────┼────────────────────┐
               │                    │                    │
           Context/Memory      Reason/Plan         Capability State
               │                    │                    │
               └────────────────────┼────────────────────┘
                                    │
                              Tool / Action Layer
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          │                         │                         │
       Gmail                     Files             Desktop Agent
                                                        │
                                        ┌───────────────┼───────────────┐
                                        │               │               │
                                      GUI            Browser        Applications
                                        │               │               │
                                      UIA/Vision        CDP          Windows APIs
                                                        
                                    ↓
                              Actual result
                                    ↓
                                Verification
                                    ↓
                              Context / Brain
```

The desktop fallback can evolve into the primary **desktop capability layer** rather than remaining forever as a mysterious emergency path. The name "fallback" describes its current origin, not necessarily its final architectural role.

---

# 36. Merge principles for future agents

### Do not blindly merge duplicate abstractions

If both projects have an intent model, compare contracts before choosing one.

If both have planners, determine whether one handles semantic reasoning and the other handles desktop execution planning. They may need different roles, not deletion by default.

If both have executors, keep clear boundaries between:

```text
logical/application operations
```

and:

```text
real desktop/browser operations
```

### Do not create a chain of translators

Avoid unnecessary patterns like:

```text
Intent A
 → Intent B
 → Task intent
 → Planner intent
 → Action intent
 → Executor intent
```

unless a boundary is genuinely required.

### Preserve the strongest existing contracts

Especially valuable contracts include:

- normalized `LLMResponse`
- structured telemetry
- bounded short-term context
- evidence-oriented memory retrieval
- explicit capability state
- Gmail models/service
- fallback `ActionPlan`
- fallback `ExecutionContext`
- semantic UI targets
- UIA/vision separation
- Chrome tab ownership

### Local code must remain authoritative about reality

A model can propose:

```text
save file
```

but only the actual executor/verifier can determine whether the file was saved.

---

# 37. Desired end-state behavior

ADVI should eventually support interactions like:

```text
User: Send an email to my boss saying I am ill.
ADVI: asks only for information that is genuinely missing.

User: My boss is Joel and his email is joel@gmail.com.
ADVI: remembers recipient identity and continues the email task.

User: Make it more formal and simple.
ADVI: modifies the existing draft/task, not a new unrelated task.

User: Before that, tell me my father's name.
ADVI: retrieves memory, answers, and preserves the email task context.

User: Anyway, let's send that email.
ADVI: understands that this refers to the still-active email task.

User: Yes, send it.
ADVI: performs the real send operation, verifies the actual result, then reports what happened.
```

The architecture needs to support this without forcing each sentence through a completely separate hard-coded mini-pipeline.

---

# 38. Long-term 27-scope product map

## Foundation

1. **Project Foundation & Runtime** — packaging, startup, configuration, lifecycle.
2. **Core I/O** — text, voice input, speech output.
3. **Normal Conversation** — natural non-task dialogue.

## Working Brain

4. **Conversation State** — current conversation/task awareness.
5. **Short-Term Memory** — bounded recent context.
6. **Long-Term Memory** — persistent user facts, relationships, sessions.
7. **Personality / Identity** — consistent ADVI identity and behavior.
8. **Self-Model** — actual available capabilities.
9. **Intent Understanding** — determine what the user wants.
10. **Planning** — reason about how to accomplish it.

## Agent

11. **Execution State** — task/progress/action state.
12. **Observability** — inspect LLM decisions and calls.
13. **Cost/Latency** — measure token/API/performance usage.
14. **Permission** — confirmation for consequential actions.

## Capabilities

15. **Gmail** — read, compose, modify, send, verify.
16. **Files** — search/read/create/edit/move/organize.
17. **Applications** — launch/focus/control desktop applications.
18. **GUI/Screen** — perceive and interact with screen controls.
19. **Browser** — search/navigate/interact/upload/download.

## Reliability

20. **Verification/Recovery/Rollback** — determine whether actions actually worked.
21. **Tool Registry** — clear discoverable capabilities.
22. **Model Routing** — choose primary/alternative/local models.
23. **Central Logging** — coherent diagnostic trail.
24. **Testing/Reliability** — unit/integration/real-machine tests.
25. **Performance** — RAM/CPU/startup/latency/resource control.

## Advanced

26. **Autonomous Workflows** — longer goal-directed operation.
27. **Self-Monitoring** — detect mistakes, adapt strategy, remain controlled.

These are product scope, not instructions to implement everything immediately.

---

# 39. Immediate implementation priority

The first milestone after the merge should remain narrow:

```text
User
 ↓
LLM
 ↓
Action Plan
 ↓
Real Computer
 ↓
Concrete Result
```

A representative acceptance scenario is:

```text
Open Notepad.
Write a short poem about the moon.
Save it on the Desktop as moon.txt.
```

Only after this foundation is integrated cleanly should the project reintroduce more advanced conversation/task/memory behavior around it.

---

# 40. Recommended merge sequence

### Step 1 — Preserve both source systems

Do not delete working legacy code immediately.

### Step 2 — Bring David's current `fallback/` into the primary codebase

Exclude `fallback-old/` unless a unique capability is discovered there.

### Step 3 — Decide the final role of the fallback executor

Determine whether it becomes:

- a desktop capability module,
- the primary desktop executor,
- or a routed alternative execution backend.

### Step 4 — Simplify duplicate brain/task abstractions

Compare primary `Intent`, `Planner`, `Task`, `Executor` with fallback `Intent`, `PlannerService`, `Action`, `ExecutionLoop`, `FallbackExecutor`.

### Step 5 — Connect real execution results back into ADVI context

The model must see concrete success/failure results and continue from them.

### Step 6 — Reintroduce memory/personality/task continuity around the proven execution core

Do not force the old giant `ConversationEngine` architecture to remain intact if a smaller design works better.

---

# 41. Known issues / architectural warnings to keep visible

1. Primary `app.py` is still orchestration-heavy.
2. Primary `ConversationEngine` is very large and owns many responsibilities.
3. Primary `TaskManager` + `TaskCoordinator` may be more elaborate than the future simplified architecture needs.
4. Primary and fallback have different intent/action schemas.
5. Primary and David snapshots contain substantially different implementations of many common core files.
6. David has duplicated `fallback-old/` and `fallback/` implementations.
7. David fallback is not currently wired into `advi.app:main`.
8. FallbackService is one-request oriented; multi-turn behavior is implemented externally in the test harness.
9. FallbackRouter currently uses a small hard-coded set of goals.
10. The fallback currently has execution/perception strength, but complete semantic verification/recovery is still a future architectural concern.
11. Primary snapshot lacks a source `pyproject.toml` despite containing egg-info metadata.
12. Current primary console banner is stale.
13. Current debugging/logging infrastructure should preserve real tracebacks.
14. Task schema and intent task-context code must remain synchronized; a historical mismatch caused a crash before intent detection could begin.
15. Do not treat retrieval similarity as truth.
16. Do not reintroduce heavyweight memory infrastructure without measured need.

---

# 42. What another AI agent should inspect first

When entering this repository, read these in roughly this order:

```text
ADVI_PROJECT_MAP.md
↓
src/advi/core/config.py
src/advi/core/runtime.py
src/advi/providers/base.py
src/advi/providers/groq.py
src/advi/providers/gemini.py
↓
src/advi/core/conversation.py
src/advi/core/intent_detector.py
src/advi/core/planner.py
src/advi/core/task.py
src/advi/core/task_manager.py
src/advi/core/task_coordinator.py
src/advi/core/executor.py
↓
src/advi/memory/*
src/advi/integrations/gmail/*
↓
src/advi/fallback/*
```

For any merge decision, inspect both the calling side and the called side before changing a contract.

---

# 43. Primary source inventory — actual Python code

The following inventory is generated directly from the supplied primary source snapshot. It lists classes, public/private methods and top-level functions detected by AST parsing. It is intentionally mechanical so an AI agent can locate symbols quickly.

### `__init__.py` — 3 lines / 79 bytes

### `app.py` — 272 lines / 6,091 bytes
- **Top-level imports:** `__future__`, `advi.core`, `logging`, `.memory.short_term`, `.memory.consolidator`, `.memory.retriever`, `.core.conversation`, `advi.core.intent_detector`, `advi.core.planner`, `advi.core.executor`, `advi.core.task_coordinator`, `advi.core.intent_handler`, `advi.core.memory_resolver`, `.core.runtime`, `advi.core.llm_telemetry`, `advi.core.pipeline_trace`, `advi.integrations.gmail`, `.io.console`, `.io.output`, `.io.tts`, `.providers`
- **Function:** `main()`
- **Function:** `_consolidate_session(conversation, consolidator, runtime)`
- **Function:** `_get_session_summary(runtime)`

### `brain/__init__.py` — 1 lines / 53 bytes

### `core/capabilities.py` — 184 lines / 4,776 bytes
- **Top-level imports:** `__future__`, `dataclasses`, `enum`
- **Class:** `CapabilityStatus (str, Enum)` — Current operational status of an ADVI capability.
- **Class:** `Capability` — Description of one capability known to ADVI.
- **Function:** `get_capability(name)` — Return a capability by name.
- **Function:** `available_capabilities()` — Return capabilities that ADVI can currently use.
- **Function:** `unavailable_capabilities()` — Return capabilities that ADVI cannot currently use.
- **Function:** `capability_summary()` — Produce a compact human-readable capability summary.
- **Function:** `can_use(name)` — Return True only when a capability is currently available.
- **Function:** `capability_for_prompt(email_available)` — Build compact capability context for the language model.

### `core/config.py` — 63 lines / 1,462 bytes
- **Top-level imports:** `__future__`, `dataclasses`, `pathlib`, `os`, `dotenv`
- **Class:** `Settings`
- **Function:** `load_settings()`

### `core/conversation.py` — 1618 lines / 53,435 bytes
- **Top-level imports:** `__future__`, `dataclasses`, `json`, `logging`, `..io.output`, `.task`, `.executor`, `..memory.retriever`, `..memory.session`, `..memory.short_term`, `..providers`, `.capabilities`, `.intent`, `.intent_detector`, `.intent_handler`, `.personality`, `.pipeline_trace`, `.response_policy`, `.task_coordinator`, `.llm_telemetry`, `..io.dev_display`
- **Class:** `ConversationEngine`
  - `respond(self, user_input)`
  - `_compose_email_draft(self, intent)` — Let Groq compose the complete email.
  - `_resume_email_task(self, task, email_address)` — Resume an email task after the user supplies a recipient.
  - `_format_memory_operation_context(intent, result)`
  - `get_session_buffer(self)`

### `core/executor.py` — 440 lines / 11,836 bytes
- **Top-level imports:** `__future__`, `dataclasses`, `logging`, `typing`, `.pipeline_trace`, `.planner`, `..integrations.gmail`
- **Class:** `ExecutionResult`
- **Class:** `Executor` — Execute approved planner actions.
  - `__init__(self, memory, retriever, intent_handler, gmail_service)`
  - `execute(self, step)`
  - `_execute_memory_retrieval(self, step)`
  - `_execute_memory_update(self, step)`
  - `_execute_memory_forget(self, step)`
  - `_execute_capability_query(self, step)`
  - `_execute_identity_query(self, step)`
  - `_execute_conversation(self, step)`
  - `_execute_email_draft_create(self, step)`
  - `_execute_email_draft_read(self, step)`
  - `_execute_email_draft_update(self, step)`
  - `_execute_email_send(self, step)`

### `core/intent.py` — 55 lines / 1,460 bytes
- **Top-level imports:** `__future__`, `dataclasses`, `enum`
- **Class:** `IntentType (str, Enum)`
- **Class:** `Intent`
  - `__post_init__(self)`

### `core/intent_detector.py` — 777 lines / 22,182 bytes
- **Top-level imports:** `__future__`, `json`, `logging`, `typing`, `..providers`, `.intent`, `.llm_telemetry`, `.pipeline_trace`, `.task`
- **Class:** `IntentDetector` — Detect the user's primary intent using an LLM.
  - `__init__(self, provider, telemetry)`
  - `_build_task_context(self)`
  - `set_current_task(self, task)`
  - `detect(self, user_input)`
  - `_parse(text, original_input)`

### `core/intent_handler.py` — 145 lines / 3,635 bytes
- **Top-level imports:** `__future__`, `logging`, `..memory.long_term`, `..memory.retriever`, `.intent`, `.intent_detector`, `.memory_resolver`
- **Class:** `IntentHandler` — Coordinates persistent-memory operations.
  - `__init__(self, detector, memory_resolver, memory, retriever)`
  - `handle(self, user_input, intent)` — Handle a persistent-memory intent.
  - `_apply_memory_decision(self, decision)`
  - `_forget_memory(self, user_input, intent)` — Forget an explicitly targeted memory when possible.

### `core/llm_telemetry.py` — 90 lines / 2,077 bytes
- **Top-level imports:** `__future__`, `dataclasses`
- **Class:** `LLMCallRecord`
  - `total_tokens(self)`
- **Class:** `LLMTelemetry` — Collect LLM call metrics for the current process.
  - `__init__(self)`
  - `record(self, response, purpose)`
  - `total_calls(self)`
  - `total_input_tokens(self)`
  - `total_output_tokens(self)`
  - `total_tokens(self)`
  - `total_latency_ms(self)`
  - `records_since(self, start_index)`

### `core/local_responses.py` — 53 lines / 1,287 bytes
- **Top-level imports:** `__future__`
- **Function:** `format_memory_answer(user_input, value)`
- **Function:** `format_identity_answer(user_input)`
- **Function:** `format_capability_answer()`

### `core/logging.py` — 36 lines / 1,037 bytes
- **Top-level imports:** `__future__`, `logging`, `pathlib`
- **Class:** `AdviFormatter (logging.Formatter)` — Single foundation-level log format; user-facing output comes later.
  - `format(self, record)`
- **Function:** `configure_logging(log_root)`

### `core/memory_context.py` — 24 lines / 510 bytes
- **Top-level imports:** `__future__`, `..memory.retriever`
- **Class:** `MemoryContextBuilder`
  - `build(memories)`

### `core/memory_resolver.py` — 310 lines / 7,576 bytes
- **Top-level imports:** `__future__`, `json`, `logging`, `dataclasses`, `enum`, `..memory.long_term`, `..providers`, `.llm_telemetry`
- **Class:** `MemoryOperation (str, Enum)`
- **Class:** `MemoryDecision`
  - `__post_init__(self)`
- **Class:** `MemoryResolver` — Resolve a memory-update request against relevant existing memory.
  - `__init__(self, provider, memory, telemetry)`
  - `resolve(self, user_input)`
  - `_parse(text)`
  - `_optional_string(value)`
  - `_ignore(reason)`

### `core/personality.py` — 103 lines / 3,410 bytes
- **Top-level imports:** `__future__`
- **Function:** `build_advi_system_prompt()` — Build ADVI's stable identity and behavioral system prompt.

### `core/pipeline_trace.py` — 432 lines / 12,501 bytes
- **Top-level imports:** `__future__`, `contextvars`, `json`, `logging`, `re`, `traceback`, `uuid`, `dataclasses`, `datetime`, `enum`, `typing`
- **Function:** `begin_turn(user_input)` — Start a new correlated trace for one user turn.
- **Function:** `set_task_id(task_id)`
- **Function:** `record_summary(**fields)` — Accumulate turn-level summary fields for end-of-turn output.
- **Function:** `boundary(component, phase, **fields)` — Log an ENTER/EXIT or intermediate pipeline boundary.
- **Function:** `emit_turn_summary()` — Print a compact end-of-turn diagnostic summary.
- **Function:** `next_llm_call_id()`
- **Function:** `current_turn_id()`
- **Function:** `current_task_id()`
- **Function:** `current_llm_call_id()`
- **Function:** `_sanitize_string(value)`
- **Function:** `_maybe_truncate(value)`
- **Function:** `_domain_type_name(value)`
- **Function:** `safe_repr(value)` — JSON-safe representation; redacts secrets; marks huge values.
- **Function:** `_serialize_value(value)`
- **Function:** `intent_to_dict(intent)`
- **Function:** `plan_to_dict(plan)`
- **Function:** `task_to_dict(task)`
- **Function:** `execution_result_to_dict(result)`
- **Function:** `llm_response_to_dict(response)`
- **Function:** `_format_prefix(stage)`
- **Function:** `trace(stage, **fields)` — Emit one structured trace line for a pipeline boundary.
- **Function:** `trace_exception(stage, exc, **fields)` — Log a pipeline exception with full traceback.
- **Function:** `trace_state_transition(component, action, before, after, task_id, current_task_id_before, current_task_id_after, **fields)` — Log before/after state for TaskManager and similar mutations.

### `core/planner.py` — 939 lines / 25,408 bytes
- **Top-level imports:** `__future__`, `json`, `dataclasses`, `enum`, `typing`, `.intent`, `.pipeline_trace`
- **Class:** `PlanStatus (str, Enum)`
- **Class:** `PlanStep`
- **Class:** `Plan`
  - `__post_init__(self)`
- **Class:** `Planner` — LLM-backed planner.
  - `__init__(self, provider)`
  - `create_plan(self, intent, current_task_context)` — Create a complete plan from the recognized intent.
  - `decide_next_step(self, intent, task_context, executed_step, execution_result)` — Ask Gemini what should happen after one executed step.
  - `_parse_next_step(text)`
  - `_llm_plan(self, intent, current_task_context)`
  - `_parse_plan(cls, text, intent)`
  - `_fallback_plan(intent)` — Compatibility fallback for tests/offline operation.
- **Function:** `plan_to_dict(plan)`
- **Function:** `plan_to_json(plan)`

### `core/response_policy.py` — 86 lines / 2,161 bytes
- **Top-level imports:** `__future__`
- **Function:** `detect_response_mode(user_input)` — Detect the requested response depth using simple deterministic rules.
- **Function:** `build_response_policy(user_input)` — Return response instructions appropriate for the request.

### `core/runtime.py` — 54 lines / 1,666 bytes
- **Top-level imports:** `__future__`, `dataclasses`, `logging`, `pathlib`, `.config`, `.logging`
- **Class:** `Runtime`
  - `create(cls)`
  - `start(self)`
  - `shutdown(self)`

### `core/task.py` — 77 lines / 1,658 bytes
- **Top-level imports:** `__future__`, `dataclasses`, `enum`, `typing`
- **Class:** `TaskStatus (str, Enum)`
- **Class:** `TaskStatus (str, Enum)`
- **Class:** `TaskStepStatus (str, Enum)`
- **Class:** `ConfirmationStatus (str, Enum)`
- **Class:** `ConfirmationRequest`
- **Class:** `TaskStepState`
- **Class:** `Task`

### `core/task_coordinator.py` — 946 lines / 28,167 bytes
- **Top-level imports:** `__future__`, `json`, `logging`, `dataclasses`, `.executor`, `.intent`, `.pipeline_trace`, `.planner`, `.task`, `.task_manager`
- **Class:** `TaskExecution`
- **Class:** `TaskCoordinator` — Coordinate intent planning and safe execution.
  - `current_task(self)`
  - `__init__(self, planner, executor, task_manager)`
  - `handle_task_intent(self, intent)`
  - `pause_current_task(self)`
  - `resume_last_paused_task(self)`
  - `_normalize_email_recipient(recipient)` — Convert a user/display recipient into the plain email address
  - `modify_current_task(self, updates)`
  - `get_current_task_context(self)`
  - `readback_current_task(self)`
  - `resolve_email_recipient(self, recipient_name)`
  - `missing_email_recipient(self, intent)`
  - `run(self, intent)`

### `core/task_manager.py` — 546 lines / 16,044 bytes
- **Top-level imports:** `__future__`, `uuid`, `json`, `.pipeline_trace`, `.task`
- **Class:** `TaskManager` — Manage the lifecycle of running tasks.
  - `__init__(self)`
  - `_log_transition(self, operation, task_id, before, after, current_task_id_before, **extra)`
  - `create(self, actions)`
  - `update_context(self, task_id, updates)`
  - `get_context(self, task_id)`
  - `current_task(self)`
  - `pause_current(self)`
  - `resume_last_paused(self)`
  - `paused_tasks(self)`
  - `invalidate_confirmation(self, task_id)`
  - `get(self, task_id)`
  - `start(self, task_id)`
  - `pause(self, task_id)`
  - `resume(self, task_id)`
  - `await_input(self, task_id)`
  - `await_confirmation(self, task_id, action, summary)`
  - `approve(self, task_id)`
  - `reject(self, task_id)`
  - `append_step(self, task_id, action)`
  - `start_step(self, task_id, index)`
  - `complete_step(self, task_id, index, result)`
  - `fail_step(self, task_id, index, error)`
  - `cancel(self, task_id)`
  - `_require(self, task_id)`

### `integrations/gmail/__init__.py` — 11 lines / 174 bytes
- **Top-level imports:** `.models`, `.service`

### `integrations/gmail/auth.py` — 83 lines / 1,762 bytes
- **Top-level imports:** `__future__`, `pathlib`, `google.auth.transport.requests`, `google.oauth2.credentials`, `google_auth_oauthlib.flow`
- **Function:** `get_gmail_credentials()`

### `integrations/gmail/models.py` — 22 lines / 385 bytes
- **Top-level imports:** `__future__`, `dataclasses`
- **Class:** `GmailMessage`
- **Class:** `GmailDraft`

### `integrations/gmail/service.py` — 503 lines / 12,084 bytes
- **Top-level imports:** `__future__`, `base64`, `email.mime.text`, `googleapiclient.discovery`, `...core.pipeline_trace`, `.auth`, `.models`
- **Class:** `GmailService` — Small wrapper around the Gmail API used by ADVI.
  - `__init__(self)`
  - `search_messages(self, query, limit)`
  - `search_parsed_messages(self, query, limit)`
  - `get_message(self, message_id)`
  - `get_parsed_message(self, message_id)`
  - `_extract_body(payload)`
  - `_decode_body(data)`
  - `create_draft(self, to, subject, body)`
  - `get_draft(self, draft_id)`
  - `update_draft(self, draft_id, to, subject, body)`
  - `send_draft(self, draft_id)`

### `io/__init__.py` — 1 lines / 29 bytes

### `io/console.py` — 14 lines / 299 bytes
- **Top-level imports:** `__future__`
- **Function:** `print_banner()`
- **Function:** `read_line()`
- **Function:** `print_shutdown()`

### `io/dev_display.py` — 143 lines / 3,560 bytes
- **Top-level imports:** `__future__`, `typing`
- **Function:** `_line()`
- **Function:** `show_section(title)`
- **Function:** `show_intent(intent)`
- **Function:** `show_plan(plan)`
- **Function:** `show_task(task)`
- **Function:** `show_llm_summary(records)`

### `io/output.py` — 164 lines / 4,657 bytes
- **Top-level imports:** `__future__`, `dataclasses`, `re`, `.tts`
- **Class:** `AdviResponse` — A logical response with independent display and speech representations.
  - `for_display(self)`
  - `for_speech(self)`
- **Class:** `OutputManager` — Delivers one logical response to available output channels.
  - `__init__(self, tts)`
  - `deliver(self, response)` — Display the response and attempt voice output.

### `io/tts.py` — 112 lines / 3,046 bytes
- **Top-level imports:** `__future__`, `logging`, `pathlib`, `re`, `subprocess`
- **Class:** `PiperTTS`
  - `__init__(self, executable, model, output_wav)`
  - `available(self)`
  - `synthesize(self, text)` — Convert text into a WAV file without playing it.
  - `speak(self, text)` — Synthesize speech and play it immediately.
- **Function:** `clean_for_speech(text)`
- **Function:** `play_wav(wav_path)` — Play a WAV file using Windows' native audio playback.

### `memory/__init__.py` — 1 lines / 57 bytes

### `memory/consolidator.py` — 333 lines / 8,039 bytes
- **Top-level imports:** `__future__`, `dataclasses`, `json`, `..providers`
- **Class:** `MemoryCandidate`
- **Class:** `RelationshipCandidate`
- **Class:** `ConsolidationResult`
- **Class:** `SessionConsolidator` — Extract durable information from a completed session.
  - `__init__(self, provider)`
  - `consolidate(self, messages)`
  - `_parse(text)`

### `memory/long_term.py` — 1297 lines / 36,176 bytes
- **Top-level imports:** `__future__`, `dataclasses`, `re`, `sqlite3`, `pathlib`, `typing`
- **Class:** `Relationship`
- **Class:** `Memory`
- **Class:** `MemoryHistory`
- **Class:** `Contact`
- **Class:** `LongTermMemory` — Persistent memory backed by SQLite.
  - `__init__(self, database_path)`
  - `_connect(self)`
  - `_initialize(self)`
  - `all(self)`
  - `remember(self, category, key, value, statement, confidence)`
  - `history(self, category, key, limit)`
  - `normalize_email(value)` — Return a plain valid email address or None.
  - `extract_email(cls, value)` — Extract exactly one email address from free-form user text.
  - `get_contact(self, name)`
  - `save_contact(self, name, email)`
  - `recent_sessions(self, limit)`
  - `recall(self, category, key)`
  - `search(self, query, limit)`
  - `forget(self, category, key)`
  - `clear(self)`
  - `start_session(self)`
  - `end_session(self, session_id, summary)`
  - `remember_relationship(self, subject, relation, object, confidence)`
  - `find_relationships(self, subject, relation, object, limit)`
  - `search_relationships(self, query, limit)` — Find relationships relevant to a natural-language query.
  - `related_entities(self, entity, max_hops, limit)` — Find relationships connected to an entity.
  - `save_consolidation(self, result)`
  - `latest_session(self)`

### `memory/retriever.py` — 163 lines / 4,009 bytes
- **Top-level imports:** `__future__`, `dataclasses`, `typing`, `numpy`, `.long_term`
- **Class:** `RetrievedMemory`
- **Class:** `MemoryRetriever` — Hybrid local semantic + lexical memory retrieval.
  - `__init__(self, memory, model_name)`
  - `model(self)`
  - `_memory_text(self, memory)`
  - `refresh(self)` — Refresh the memory list without loading the
  - `_ensure_embeddings(self)`
  - `search(self, query, limit)`

### `memory/session.py` — 28 lines / 692 bytes
- **Top-level imports:** `__future__`, `dataclasses`
- **Class:** `SessionBuffer` — Temporary staging area for conversation history.
  - `add(self, messages)`
  - `drain(self)`
  - `count(self)`
  - `clear(self)`

### `memory/short_term.py` — 62 lines / 1,403 bytes
- **Top-level imports:** `__future__`, `dataclasses`
- **Class:** `ShortTermMemory` — Bounded conversation memory for the current ADVI session.
  - `add(self, role, content)`
  - `_trim(self)`
  - `get_messages(self)`
  - `remove_last(self)`
  - `clear(self)`
  - `count(self)`

### `personality/__init__.py` — 1 lines / 61 bytes

### `providers/__init__.py` — 26 lines / 514 bytes
- **Top-level imports:** `.base`, `.errors`, `.groq`, `.gemini`

### `providers/base.py` — 63 lines / 1,662 bytes
- **Top-level imports:** `__future__`, `abc`, `dataclasses`
- **Class:** `LLMResponse` — Normalized response returned by every LLM provider.
- **Class:** `LLMProvider (ABC)` — Common interface for all ADVI language-model providers.
  - `name(self)` — Human-readable provider identifier.
  - `model(self)` — Active model identifier.
  - `chat(self, messages)` — Send a conversation and return a normalized response.
  - `structured(self, messages, schema)` — Send a structured-output request.

### `providers/errors.py` — 25 lines / 583 bytes
- **Top-level imports:** `__future__`
- **Class:** `LLMError (Exception)` — Base error for all ADVI LLM failures.
- **Class:** `LLMAuthenticationError (LLMError)` — Provider rejected the supplied credentials.
- **Class:** `LLMRateLimitError (LLMError)` — Provider rejected the request because of quota/rate limits.
- **Class:** `LLMTimeoutError (LLMError)` — Provider request timed out.
- **Class:** `LLMUnavailableError (LLMError)` — Provider is temporarily unavailable.
- **Class:** `LLMResponseError (LLMError)` — Provider returned an unusable response.

### `providers/gemini.py` — 489 lines / 13,663 bytes
- **Top-level imports:** `__future__`, `logging`, `time`, `datetime`, `google`, `google.genai`, `..core.pipeline_trace`, `.base`, `.errors`, `.gemini_trace`
- **Class:** `GeminiProvider (LLMProvider)` — Gemini-backed LLM provider.
  - `__init__(self, api_key, model)`
  - `name(self)`
  - `model(self)`
  - `chat(self, messages)` — Send a normal conversational request to Gemini.
  - `structured(self, messages, schema)` — Generate schema-constrained JSON using Gemini.

### `providers/gemini_trace.py` — 192 lines / 5,713 bytes
- **Top-level imports:** `__future__`, `typing`
- **Function:** `gemini_response_to_trace_dict(response)` — Extract traceable metadata from a raw Gemini GenerateContentResponse.
- **Function:** `_candidate_to_dict(candidate)`
- **Function:** `gemini_config_to_trace_dict(config)` — Serialize GenerateContentConfig fields for trace logging.
- **Function:** `_system_instruction_text(value)`
- **Function:** `gemini_contents_to_trace_list(contents)`

### `providers/groq.py` — 228 lines / 6,283 bytes
- **Top-level imports:** `__future__`, `logging`, `time`, `datetime`, `groq`, `groq`, `..core.pipeline_trace`, `.base`, `.errors`
- **Class:** `GroqProvider (LLMProvider)` — Groq-backed LLM provider.
  - `__init__(self, api_key, model)`
  - `name(self)`
  - `model(self)`
  - `chat(self, messages)`

### `tools/__init__.py` — 1 lines / 39 bytes

---

# 44. David source inventory — actual Python code

The following inventory is generated directly from the supplied David source snapshot.

### `__init__.py` — 3 lines / 79 bytes

### `app.py` — 264 lines / 5,850 bytes
- **Top-level imports:** `__future__`, `advi.core`, `logging`, `.memory.short_term`, `.memory.consolidator`, `.memory.retriever`, `.core.conversation`, `advi.core.intent_detector`, `advi.core.planner`, `advi.core.executor`, `advi.core.task_coordinator`, `advi.core.intent_handler`, `advi.core.memory_resolver`, `.core.runtime`, `advi.core.llm_telemetry`, `.io.console`, `.io.output`, `.io.tts`, `.providers`
- **Function:** `main()`
- **Function:** `_consolidate_session(conversation, consolidator, runtime)`
- **Function:** `_get_session_summary(runtime)`

### `brain/__init__.py` — 1 lines / 53 bytes

### `core/capabilities.py` — 167 lines / 4,174 bytes
- **Top-level imports:** `__future__`, `dataclasses`, `enum`
- **Class:** `CapabilityStatus (str, Enum)` — Current operational status of an ADVI capability.
- **Class:** `Capability` — Description of one capability known to ADVI.
- **Function:** `get_capability(name)` — Return a capability by name.
- **Function:** `available_capabilities()` — Return capabilities that ADVI can currently use.
- **Function:** `unavailable_capabilities()` — Return capabilities that ADVI cannot currently use.
- **Function:** `capability_summary()` — Produce a compact human-readable capability summary.
- **Function:** `can_use(name)` — Return True only when a capability is currently available.
- **Function:** `capability_for_prompt()` — Build compact capability context for the language model.

### `core/config.py` — 63 lines / 1,462 bytes
- **Top-level imports:** `__future__`, `dataclasses`, `pathlib`, `os`, `dotenv`
- **Class:** `Settings`
- **Function:** `load_settings()`

### `core/conversation.py` — 625 lines / 18,684 bytes
- **Top-level imports:** `__future__`, `dataclasses`, `json`, `logging`, `..io.output`, `..memory.retriever`, `..memory.session`, `..memory.short_term`, `..providers`, `.capabilities`, `.intent`, `.intent_detector`, `.intent_handler`, `.llm_telemetry`, `.personality`, `.response_policy`, `.task_coordinator`, `.llm_telemetry`, `..io.dev_display`
- **Class:** `ConversationEngine`
  - `respond(self, user_input)`
  - `_format_memory_operation_context(intent, result)`
  - `get_session_buffer(self)`

### `core/executor.py` — 181 lines / 4,362 bytes
- **Top-level imports:** `__future__`, `dataclasses`, `typing`, `.planner`
- **Class:** `ExecutionResult`
- **Class:** `Executor` — Execute approved planner actions.
  - `__init__(self, memory, retriever, intent_handler)`
  - `execute(self, step)`
  - `_execute_memory_retrieval(self, step)`
  - `_execute_memory_update(self, step)`
  - `_execute_memory_forget(self, step)`
  - `_execute_capability_query(self, step)`
  - `_execute_identity_query(self, step)`
  - `_execute_conversation(self, step)`

### `core/intent.py` — 51 lines / 1,254 bytes
- **Top-level imports:** `__future__`, `dataclasses`, `enum`
- **Class:** `IntentType (str, Enum)`
- **Class:** `Intent`
  - `__post_init__(self)`

### `core/intent_detector.py` — 400 lines / 9,040 bytes
- **Top-level imports:** `__future__`, `json`, `logging`, `..providers`, `.intent`, `.llm_telemetry`, `.task`
- **Class:** `IntentDetector` — Detect the user's primary intent using an LLM.
  - `__init__(self, provider, telemetry)`
  - `_build_task_context(self)`
  - `set_current_task(self, task)`
  - `detect(self, user_input)`
  - `_parse(text, original_input)`

### `core/intent_handler.py` — 145 lines / 3,491 bytes
- **Top-level imports:** `__future__`, `logging`, `..memory.long_term`, `..memory.retriever`, `.intent`, `.intent_detector`, `.memory_resolver`
- **Class:** `IntentHandler` — Coordinates persistent-memory operations.
  - `__init__(self, detector, memory_resolver, memory, retriever)`
  - `handle(self, user_input, intent)` — Handle a persistent-memory intent.
  - `_apply_memory_decision(self, decision)`
  - `_forget_memory(self, user_input, intent)` — Forget an explicitly targeted memory when possible.

### `core/llm_telemetry.py` — 90 lines / 1,988 bytes
- **Top-level imports:** `__future__`, `dataclasses`
- **Class:** `LLMCallRecord`
  - `total_tokens(self)`
- **Class:** `LLMTelemetry` — Collect LLM call metrics for the current process.
  - `__init__(self)`
  - `record(self, response, purpose)`
  - `total_calls(self)`
  - `total_input_tokens(self)`
  - `total_output_tokens(self)`
  - `total_tokens(self)`
  - `total_latency_ms(self)`
  - `records_since(self, start_index)`

### `core/local_responses.py` — 53 lines / 1,235 bytes
- **Top-level imports:** `__future__`
- **Function:** `format_memory_answer(user_input, value)`
- **Function:** `format_identity_answer(user_input)`
- **Function:** `format_capability_answer()`

### `core/logging.py` — 32 lines / 911 bytes
- **Top-level imports:** `__future__`, `logging`, `pathlib`
- **Class:** `AdviFormatter (logging.Formatter)` — Single foundation-level log format; user-facing output comes later.
  - `format(self, record)`
- **Function:** `configure_logging(log_root)`

### `core/memory_context.py` — 24 lines / 487 bytes
- **Top-level imports:** `__future__`, `..memory.retriever`
- **Class:** `MemoryContextBuilder`
  - `build(memories)`

### `core/memory_resolver.py` — 310 lines / 7,267 bytes
- **Top-level imports:** `__future__`, `json`, `logging`, `dataclasses`, `enum`, `..memory.long_term`, `..providers`, `.llm_telemetry`
- **Class:** `MemoryOperation (str, Enum)`
- **Class:** `MemoryDecision`
  - `__post_init__(self)`
- **Class:** `MemoryResolver` — Resolve a memory-update request against relevant existing memory.
  - `__init__(self, provider, memory, telemetry)`
  - `resolve(self, user_input)`
  - `_parse(text)`
  - `_optional_string(value)`
  - `_ignore(reason)`

### `core/personality.py` — 103 lines / 3,308 bytes
- **Top-level imports:** `__future__`
- **Function:** `build_advi_system_prompt()` — Build ADVI's stable identity and behavioral system prompt.

### `core/planner.py` — 124 lines / 2,800 bytes
- **Top-level imports:** `__future__`, `json`, `dataclasses`, `enum`, `.intent`
- **Class:** `PlanStatus (str, Enum)`
- **Class:** `PlanStep`
- **Class:** `Plan`
  - `__post_init__(self)`
- **Class:** `Planner` — Create a safe execution plan from a recognized intent.
  - `create_plan(self, intent)`
- **Function:** `plan_to_dict(plan)`
- **Function:** `plan_to_json(plan)`

### `core/response_policy.py` — 86 lines / 2,076 bytes
- **Top-level imports:** `__future__`
- **Function:** `detect_response_mode(user_input)` — Detect the requested response depth using simple deterministic rules.
- **Function:** `build_response_policy(user_input)` — Return response instructions appropriate for the request.

### `core/runtime.py` — 124 lines / 2,689 bytes
- **Top-level imports:** `__future__`, `dataclasses`, `logging`, `pathlib`, `.config`, `..memory.long_term`, `.logging`
- **Class:** `Runtime`
  - `create(cls)`
  - `start(self)`
  - `shutdown(self, session_summary)`

### `core/task.py` — 66 lines / 1,276 bytes
- **Top-level imports:** `__future__`, `dataclasses`, `enum`, `typing`
- **Class:** `TaskStatus (str, Enum)`
- **Class:** `TaskStepStatus (str, Enum)`
- **Class:** `ConfirmationStatus (str, Enum)`
- **Class:** `ConfirmationRequest`
- **Class:** `TaskStepState`
- **Class:** `Task`

### `core/task_coordinator.py` — 208 lines / 4,868 bytes
- **Top-level imports:** `__future__`, `dataclasses`, `.executor`, `.intent`, `.planner`, `logging`, `.task_manager`, `.task`, `.intent`, `.planner`
- **Class:** `TaskExecution`
- **Class:** `TaskCoordinator` — Coordinate intent planning and safe execution.
  - `current_task(self)`
  - `__init__(self, planner, executor, task_manager)`
  - `handle_task_intent(self, intent)`
  - `pause_current_task(self)`
  - `resume_last_paused_task(self)`
  - `modify_current_task(self, updates)`
  - `get_current_task_context(self)`
  - `run(self, intent)`

### `core/task_manager.py` — 336 lines / 7,282 bytes
- **Top-level imports:** `__future__`, `uuid`, `.task`
- **Class:** `TaskManager` — Manage the lifecycle of running tasks.
  - `__init__(self)`
  - `create(self, actions)`
  - `update_context(self, task_id, updates)`
  - `get_context(self, task_id)`
  - `current_task(self)`
  - `pause_current(self)`
  - `resume_last_paused(self)`
  - `paused_tasks(self)`
  - `invalidate_confirmation(self, task_id)`
  - `get(self, task_id)`
  - `start(self, task_id)`
  - `pause(self, task_id)`
  - `resume(self, task_id)`
  - `await_confirmation(self, task_id, action, summary)`
  - `approve(self, task_id)`
  - `reject(self, task_id)`
  - `start_step(self, task_id, index)`
  - `complete_step(self, task_id, index, result)`
  - `fail_step(self, task_id, index, error)`
  - `cancel(self, task_id)`
  - `_require(self, task_id)`

### `fallback/__init__.py` — 0 lines / 0 bytes

### `fallback/action_plan_schema.py` — 19 lines / 345 bytes
- **Top-level imports:** `__future__`, `typing`, `pydantic`
- **Class:** `Action (BaseModel)`
- **Class:** `ActionPlan (BaseModel)`

### `fallback/cdp_browser.py` — 620 lines / 25,504 bytes
- **Top-level imports:** `__future__`, `json`, `logging`, `time`, `urllib.request`, `typing`, `websocket`
- **Class:** `CDPBrowser` — Generalized Chrome DevTools Protocol (CDP) browser automation layer.
  - `__init__(self, port)`
  - `_http_get_json(self, path)`
  - `list_tabs(self)` — List all open page targets in Chrome.
  - `create_new_tab(self, url)` — Create a dedicated target tab in Chrome via CDP /json/new.
  - `get_tab_info(self, tab_id)` — Get details for a specific tab_id.
  - `execute_cdp_command(self, tab_id, method, params, timeout)` — Execute a CDP method directly on the specified tab's WebSocket debugger.
  - `evaluate_js(self, tab_id, expression, await_promise, return_by_value, timeout)` — Evaluate JavaScript in the target tab context and return the result.
  - `activate_tab(self, tab_id)` — Bring target_tab_id to active tab status within Chrome.
  - `navigate(self, tab_id, url, timeout)` — Navigate target tab to a URL and wait for DOM readiness.
  - `wait_for_dom_ready(self, tab_id, timeout)` — Wait until document.readyState is interactive or complete.
  - `find_in_site_search_input(self, tab_id)` — Locate the target website's own search input field.
  - `execute_in_site_search(self, tab_id, query)` — Enter query directly into website's search input and submit.
  - `click_relevant_result(self, tab_id, target_text)` — Locate and click the requested result element on the page.
  - `verify_action_state(self, tab_id, expected_url_contains, expected_title_contains)` — Verify tab page state (URL, title, DOM loading).

### `fallback/execution_context.py` — 89 lines / 3,288 bytes
- **Top-level imports:** `__future__`, `logging`, `dataclasses`, `typing`
- **Class:** `ExecutionContext` — Persistent execution context maintained throughout an automation plan.
  - `reset(self)` — Reset execution context between distinct user tasks.
  - `set_target_tab(self, tab_id, url, title)` — Store the identity of the automation task's target Chrome tab.
  - `set_chrome_window(self, hwnd)` — Store the HWND of the Chrome window owned by this task.
  - `set_application(self, app_name, hwnd)` — Set the active application name and optional window handle.
  - `is_chrome_target(self)` — Return True if the target application is Chrome with a valid tab ID.

### `fallback/execution_loop.py` — 178 lines / 6,668 bytes
- **Top-level imports:** `__future__`, `logging`, `dataclasses`, `typing`, `.action_plan_schema`, `.execution_context`, `.executor`, `.perception`
- **Class:** `ExecutionLoopResult`
- **Class:** `ExecutionLoop` — Execute a fallback action plan in one continuous run.
  - `__init__(self, perception, executor, context)`
  - `current_application(self)`
  - `current_application(self, value)`
  - `run(self, plan)`
  - `_ensure_current_application_focus(self, action_name)` — Ensure application focus context is active.
  - `_execute_action(self, action)`
  - `_update_context(self, action)` — Update context state following successful action execution.

### `fallback/executor.py` — 758 lines / 30,614 bytes
- **Top-level imports:** `__future__`, `ctypes`, `json`, `logging`, `os`, `subprocess`, `time`, `urllib.request`, `pathlib`, `typing`, `pyautogui`, `.action_plan_schema`, `.cdp_browser`, `.execution_context`
- **Class:** `ActionResult`
  - `__init__(self, action, success, data, error)`
  - `__repr__(self)`
- **Class:** `FallbackExecutor` — Generalized Agentic Desktop & Browser Fallback Executor.
  - `__init__(self, context)`
  - `_current_window_hwnd(self)`
  - `_current_window_hwnd(self, value)`
  - `_chrome_tab_id(self)`
  - `_chrome_tab_id(self, value)`
  - `_chrome_tab_url(self)`
  - `_chrome_tab_url(self, value)`
  - `_chrome_tab_title(self)`
  - `_chrome_tab_title(self, value)`
  - `_chrome_process_id(self)`
  - `_chrome_process_id(self, value)`
  - `_chrome_window_hwnd(self)`
  - `_chrome_window_hwnd(self, value)`
  - `execute(self, plan)`
  - `execute_action(self, action, context)`
  - `_list_chrome_tabs(self)`
  - `_verify_chrome_tab_context(self)`
  - `_list_chrome_window_hwnds()`
  - `_execute_open_application(self, action)`
  - `_normalize_application_name(application_name)`
  - `_application_matches_window(cls, application_name, hwnd)`
  - `_find_application_window(cls, application_name)`
  - `_focus_hwnd(hwnd)`
  - `ensure_application_focus(self, application_name)` — Separate logical target ownership from OS focus.
  - `_execute_navigate(self, action)`
  - `_execute_search(self, action)`
  - `_execute_click(self, action)`
  - `_execute_double_click(self, action)`
  - `_execute_right_click(self, action)`
  - `_execute_type_text(self, action)`
  - `_execute_press_key(self, action)`
  - `_execute_hotkey(self, action)`
  - `_execute_focus_window(self, action)`
  - `_execute_close_window(self, action)`
  - `_execute_wait(self, action)`
  - `_execute_scroll(self, action)`
  - `_execute_finish(self, action)`
  - `_is_coordinate_target(target)`
  - `_click_coordinate_target(target, double, right)`

### `fallback/intent_schema.py` — 19 lines / 406 bytes
- **Top-level imports:** `__future__`, `typing`, `pydantic`
- **Class:** `Intent (BaseModel)`

### `fallback/intent_service.py` — 65 lines / 1,441 bytes
- **Top-level imports:** `__future__`, `json`, `logging`, `pathlib`, `..providers`, `.intent_schema`
- **Class:** `IntentService` — Extract an agentic desktop intent from user input.
  - `__init__(self, provider, prompt_path)`
  - `extract_intent(self, user_input)`

### `fallback/perception.py` — 1235 lines / 35,047 bytes
- **Top-level imports:** `__future__`, `logging`, `dataclasses`, `typing`, `pywinauto`
- **Class:** `PerceptionResult`
- **Class:** `ScreenPerception` — Resolve semantic UI targets.
  - `__init__(self, vision)`
  - `find(self, target, action, application)`
  - `_find_window(self, target)`
  - `_find_with_uia(self, target, action, application)`
  - `_looks_like_window_target(target)`
  - `_looks_like_search_target(target)`
  - `_looks_like_text_target(target)`
  - `_extract_application_hint(target)`
  - `_window_matches_application(title, application)`
  - `_find_search_control(window)` — Find an actual search input through UIA.
  - `_control_looks_like_search(control)`
  - `_find_editable_control(window)`

### `fallback/planner_service.py` — 1161 lines / 29,970 bytes
- **Top-level imports:** `__future__`, `json`, `logging`, `pathlib`, `..providers`, `.action_plan_schema`, `.intent_schema`
- **Class:** `PlannerService` — Generate a semantic desktop action plan from an intent.
  - `__init__(self, provider, prompt_path)`
  - `generate_plan(self, intent)` — Generate an executor-ready action plan from a validated Intent.
  - `_validate_and_complete_plan(self, intent, plan)` — Validate the LLM-generated plan against the Intent.
  - `_validate_action(self, action, current_focus)` — Validate one LLM-generated Action without replacing
  - `_build_action_from_intent(self, source)` — Build an Action directly from an Intent secondary action.
  - `_build_parameters(self, action_name, source)` — Convert an Intent secondary action into a minimal
  - `_finalize_plan(self, actions)` — Final normalization of the plan.
  - `_is_valid_action(self, action)` — Check whether an action belongs to the supported

### `fallback/router.py` — 60 lines / 1,331 bytes
- **Top-level imports:** `__future__`, `dataclasses`, `.intent_schema`
- **Class:** `RouteResult`
- **Class:** `FallbackRouter` — Decide whether an agentic desktop intent should use
  - `route(self, intent)`

### `fallback/service.py` — 99 lines / 2,394 bytes
- **Top-level imports:** `__future__`, `logging`, `pathlib`, `..providers`, `.action_plan_schema`, `.execution_loop`, `.intent_schema`, `.intent_service`, `.planner_service`
- **Class:** `FallbackService` — Standalone agentic desktop fallback pipeline.
  - `__init__(self, provider, intent_prompt_path, planner_prompt_path, execution_loop)`
  - `process(self, user_input)`

### `fallback/vision.py` — 1057 lines / 29,373 bytes
- **Top-level imports:** `__future__`, `ctypes`, `logging`, `re`, `dataclasses`, `pathlib`, `typing`, `pyautogui`, `pywinauto`
- **Class:** `VisionResult`
- **Class:** `VisionPerception` — Screenshot-based visual perception fallback.
  - `__init__(self, screenshot_dir)`
  - `capture_screen(self)`
  - `find(self, target, action, application)`
  - `_find_relevant_window(application_hint)` — Find the visible desktop window corresponding to
  - `_content_top_offset(window_info)` — Estimate the amount of top browser/application chrome
  - `_find_search_target(candidates, application_hint)`
  - `_find_generic_target(candidates, target, application_hint)` — Resolve a visible page target from OCR without allowing a
  - `_extract_application_hint(target)`
  - `_looks_like_search_target(target)`
  - `_semantic_words(target)`
  - `_normalize_text(value)`
  - `_parse_confidence(value)`

### `fallback-old/__init__.py` — 0 lines / 0 bytes

### `fallback-old/action_plan_schema.py` — 19 lines / 345 bytes
- **Top-level imports:** `__future__`, `typing`, `pydantic`
- **Class:** `Action (BaseModel)`
- **Class:** `ActionPlan (BaseModel)`

### `fallback-old/execution_loop.py` — 368 lines / 9,791 bytes
- **Top-level imports:** `__future__`, `logging`, `dataclasses`, `.action_plan_schema`, `.executor`, `.perception`
- **Class:** `ExecutionLoopResult`
- **Class:** `ExecutionLoop` — Execute a fallback action plan one action at a time.
  - `__init__(self, perception, executor)`
  - `run(self, plan)`
  - `_ensure_current_application_focus(self, action_name)` — Restore the current application's foreground focus.
  - `_execute_action(self, action)` — Execute one action while preserving the current
  - `_update_context(self, action)` — Update execution context after a successful action.

### `fallback-old/executor.py` — 2079 lines / 54,310 bytes
- **Top-level imports:** `logging`, `os`, `ctypes`, `subprocess`, `time`, `json`, `urllib.request`, `websocket`, `dataclasses`, `pathlib`, `typing`, `pyautogui`, `.action_plan_schema`
- **Class:** `ActionResult`
- **Class:** `FallbackExecutor` — Execute semantic desktop actions produced by the
  - `__init__(self)`
  - `execute(self, plan)`
  - `execute_action(self, action)`
  - `_cdp_http_json(self, path)`
  - `_list_chrome_tabs(self)`
  - `_cdp_browser_command(self, method, params)`
  - `_activate_chrome_tab(self, tab_id)`
  - `_find_replacement_chrome_tab(self)`
  - `_list_chrome_window_hwnds()`
  - `_find_window_for_process_id(self, process_id)`
  - `_verify_chrome_tab_context(self)`
  - `_capture_new_chrome_tab(self, before_ids)`
  - `_remember_chrome_tab(self, tab)`
  - `_execute_open_application(self, action)`
  - `_normalize_application_name(application_name)`
  - `_application_matches_window(cls, application_name, hwnd)` — Match a top-level window to an application.
  - `_find_application_window(cls, application_name)` — Find a visible, non-minimized top-level window belonging to
  - `_focus_hwnd(hwnd)` — Restore and activate a specific top-level HWND.
  - `_focus_application_window(self, application_name)` — Focus the requested application.
  - `ensure_application_focus(self, application_name)` — Re-focus the application owning the current execution context.
  - `_execute_focus_window(self, action)`
  - `_execute_close_window(self, action)`
  - `_execute_wait(self, action)`
  - `_execute_click(self, action)`
  - `_execute_double_click(self, action)`
  - `_execute_right_click(self, action)`
  - `_execute_type_text(self, action)`
  - `_execute_press_key(self, action)`
  - `_execute_hotkey(self, action)`
  - `_execute_search(self, action)`
  - `_execute_navigate(self, action)`
  - `_execute_scroll(self, action)`
  - `_execute_finish(self, action)`
  - `_is_coordinate_target(target)` — Determine whether perception returned a visual
  - `_click_coordinate_target(target, double, right)`

### `fallback-old/intent_schema.py` — 19 lines / 406 bytes
- **Top-level imports:** `__future__`, `typing`, `pydantic`
- **Class:** `Intent (BaseModel)`

### `fallback-old/intent_service.py` — 65 lines / 1,441 bytes
- **Top-level imports:** `__future__`, `json`, `logging`, `pathlib`, `..providers`, `.intent_schema`
- **Class:** `IntentService` — Extract an agentic desktop intent from user input.
  - `__init__(self, provider, prompt_path)`
  - `extract_intent(self, user_input)`

### `fallback-old/perception.py` — 1220 lines / 34,307 bytes
- **Top-level imports:** `__future__`, `logging`, `dataclasses`, `typing`, `pywinauto`
- **Class:** `PerceptionResult`
- **Class:** `ScreenPerception` — Resolve semantic UI targets.
  - `__init__(self, vision)`
  - `find(self, target, action, application)`
  - `_find_window(self, target)`
  - `_find_with_uia(self, target, action, application)`
  - `_looks_like_window_target(target)`
  - `_looks_like_search_target(target)`
  - `_looks_like_text_target(target)`
  - `_extract_application_hint(target)`
  - `_window_matches_application(title, application)`
  - `_find_search_control(window)` — Find an actual search input through UIA.
  - `_control_looks_like_search(control)`
  - `_find_editable_control(window)`

### `fallback-old/planner_service.py` — 1161 lines / 29,970 bytes
- **Top-level imports:** `__future__`, `json`, `logging`, `pathlib`, `..providers`, `.action_plan_schema`, `.intent_schema`
- **Class:** `PlannerService` — Generate a semantic desktop action plan from an intent.
  - `__init__(self, provider, prompt_path)`
  - `generate_plan(self, intent)` — Generate an executor-ready action plan from a validated Intent.
  - `_validate_and_complete_plan(self, intent, plan)` — Validate the LLM-generated plan against the Intent.
  - `_validate_action(self, action, current_focus)` — Validate one LLM-generated Action without replacing
  - `_build_action_from_intent(self, source)` — Build an Action directly from an Intent secondary action.
  - `_build_parameters(self, action_name, source)` — Convert an Intent secondary action into a minimal
  - `_finalize_plan(self, actions)` — Final normalization of the plan.
  - `_is_valid_action(self, action)` — Check whether an action belongs to the supported

### `fallback-old/router.py` — 60 lines / 1,331 bytes
- **Top-level imports:** `__future__`, `dataclasses`, `.intent_schema`
- **Class:** `RouteResult`
- **Class:** `FallbackRouter` — Decide whether an agentic desktop intent should use
  - `route(self, intent)`

### `fallback-old/service.py` — 99 lines / 2,394 bytes
- **Top-level imports:** `__future__`, `logging`, `pathlib`, `..providers`, `.action_plan_schema`, `.execution_loop`, `.intent_schema`, `.intent_service`, `.planner_service`
- **Class:** `FallbackService` — Standalone agentic desktop fallback pipeline.
  - `__init__(self, provider, intent_prompt_path, planner_prompt_path, execution_loop)`
  - `process(self, user_input)`

### `fallback-old/vision.py` — 1057 lines / 29,373 bytes
- **Top-level imports:** `__future__`, `ctypes`, `logging`, `re`, `dataclasses`, `pathlib`, `typing`, `pyautogui`, `pywinauto`
- **Class:** `VisionResult`
- **Class:** `VisionPerception` — Screenshot-based visual perception fallback.
  - `__init__(self, screenshot_dir)`
  - `capture_screen(self)`
  - `find(self, target, action, application)`
  - `_find_relevant_window(application_hint)` — Find the visible desktop window corresponding to
  - `_content_top_offset(window_info)` — Estimate the amount of top browser/application chrome
  - `_find_search_target(candidates, application_hint)`
  - `_find_generic_target(candidates, target, application_hint)` — Resolve a visible page target from OCR without allowing a
  - `_extract_application_hint(target)`
  - `_looks_like_search_target(target)`
  - `_semantic_words(target)`
  - `_normalize_text(value)`
  - `_parse_confidence(value)`

### `io/__init__.py` — 1 lines / 29 bytes

### `io/console.py` — 14 lines / 299 bytes
- **Top-level imports:** `__future__`
- **Function:** `print_banner()`
- **Function:** `read_line()`
- **Function:** `print_shutdown()`

### `io/dev_display.py` — 143 lines / 3,418 bytes
- **Top-level imports:** `__future__`, `typing`
- **Function:** `_line()`
- **Function:** `show_section(title)`
- **Function:** `show_intent(intent)`
- **Function:** `show_plan(plan)`
- **Function:** `show_task(task)`
- **Function:** `show_llm_summary(records)`

### `io/output.py` — 164 lines / 4,494 bytes
- **Top-level imports:** `__future__`, `dataclasses`, `re`, `.tts`
- **Class:** `AdviResponse` — A logical response with independent display and speech representations.
  - `for_display(self)`
  - `for_speech(self)`
- **Class:** `OutputManager` — Delivers one logical response to available output channels.
  - `__init__(self, tts)`
  - `deliver(self, response)` — Display the response and attempt voice output.

### `io/tts.py` — 112 lines / 3,046 bytes
- **Top-level imports:** `__future__`, `logging`, `pathlib`, `re`, `subprocess`
- **Class:** `PiperTTS`
  - `__init__(self, executable, model, output_wav)`
  - `available(self)`
  - `synthesize(self, text)` — Convert text into a WAV file without playing it.
  - `speak(self, text)` — Synthesize speech and play it immediately.
- **Function:** `clean_for_speech(text)`
- **Function:** `play_wav(wav_path)` — Play a WAV file using Windows' native audio playback.

### `memory/__init__.py` — 1 lines / 57 bytes

### `memory/consolidator.py` — 311 lines / 6,929 bytes
- **Top-level imports:** `__future__`, `dataclasses`, `json`, `..providers`
- **Class:** `MemoryCandidate`
- **Class:** `MemoryCandidate`
- **Class:** `RelationshipCandidate`
- **Class:** `ConsolidationResult`
- **Class:** `SessionConsolidator` — Extract durable information from a completed session.
  - `__init__(self, provider)`
  - `consolidate(self, messages)`
  - `_parse(text)`

### `memory/long_term.py` — 1109 lines / 30,431 bytes
- **Top-level imports:** `__future__`, `dataclasses`, `re`, `sqlite3`, `pathlib`, `typing`
- **Class:** `Relationship`
- **Class:** `Memory`
- **Class:** `MemoryHistory`
- **Class:** `LongTermMemory` — Persistent memory backed by SQLite.
  - `__init__(self, database_path)`
  - `_connect(self)`
  - `_initialize(self)`
  - `all(self)`
  - `remember(self, category, key, value, statement, confidence)`
  - `history(self, category, key, limit)`
  - `recent_sessions(self, limit)`
  - `recall(self, category, key)`
  - `search(self, query, limit)`
  - `forget(self, category, key)`
  - `clear(self)`
  - `start_session(self)`
  - `end_session(self, session_id, summary)`
  - `remember_relationship(self, subject, relation, object, confidence)`
  - `find_relationships(self, subject, relation, object, limit)`
  - `search_relationships(self, query, limit)` — Find relationships relevant to a natural-language query.
  - `related_entities(self, entity, max_hops, limit)` — Find relationships connected to an entity.
  - `save_consolidation(self, result)`
  - `latest_session(self)`

### `memory/retriever.py` — 163 lines / 3,847 bytes
- **Top-level imports:** `__future__`, `dataclasses`, `typing`, `numpy`, `.long_term`
- **Class:** `RetrievedMemory`
- **Class:** `MemoryRetriever` — Hybrid local semantic + lexical memory retrieval.
  - `__init__(self, memory, model_name)`
  - `model(self)`
  - `_memory_text(self, memory)`
  - `refresh(self)` — Refresh the memory list without loading the
  - `_ensure_embeddings(self)`
  - `search(self, query, limit)`

### `memory/session.py` — 28 lines / 665 bytes
- **Top-level imports:** `__future__`, `dataclasses`
- **Class:** `SessionBuffer` — Temporary staging area for conversation history.
  - `add(self, messages)`
  - `drain(self)`
  - `count(self)`
  - `clear(self)`

### `memory/short_term.py` — 62 lines / 1,342 bytes
- **Top-level imports:** `__future__`, `dataclasses`
- **Class:** `ShortTermMemory` — Bounded conversation memory for the current ADVI session.
  - `add(self, role, content)`
  - `_trim(self)`
  - `get_messages(self)`
  - `remove_last(self)`
  - `clear(self)`
  - `count(self)`

### `personality/__init__.py` — 1 lines / 61 bytes

### `providers/__init__.py` — 26 lines / 514 bytes
- **Top-level imports:** `.base`, `.errors`, `.groq`, `.gemini`

### `providers/base.py` — 48 lines / 1,130 bytes
- **Top-level imports:** `__future__`, `abc`, `dataclasses`
- **Class:** `LLMResponse` — Normalized response returned by every LLM provider.
- **Class:** `LLMProvider (ABC)` — Common interface for all ADVI language-model providers.
  - `name(self)` — Human-readable provider identifier.
  - `model(self)` — Active model identifier.
  - `chat(self, messages)` — Send a conversation and return a normalized response.

### `providers/errors.py` — 25 lines / 559 bytes
- **Top-level imports:** `__future__`
- **Class:** `LLMError (Exception)` — Base error for all ADVI LLM failures.
- **Class:** `LLMAuthenticationError (LLMError)` — Provider rejected the supplied credentials.
- **Class:** `LLMRateLimitError (LLMError)` — Provider rejected the request because of quota/rate limits.
- **Class:** `LLMTimeoutError (LLMError)` — Provider request timed out.
- **Class:** `LLMUnavailableError (LLMError)` — Provider is temporarily unavailable.
- **Class:** `LLMResponseError (LLMError)` — Provider returned an unusable response.

### `providers/gemini.py` — 151 lines / 3,586 bytes
- **Top-level imports:** `__future__`, `time`, `google`, `.base`, `.errors`
- **Class:** `GeminiProvider (LLMProvider)` — Gemini-backed LLM provider.
  - `__init__(self, api_key, model)`
  - `name(self)`
  - `model(self)`
  - `chat(self, messages)`
  - `_to_prompt(messages)`

### `providers/groq.py` — 119 lines / 2,799 bytes
- **Top-level imports:** `__future__`, `time`, `groq`, `groq`, `.base`, `.errors`
- **Class:** `GroqProvider (LLMProvider)` — Groq-backed LLM provider.
  - `__init__(self, api_key, model)`
  - `name(self)`
  - `model(self)`
  - `chat(self, messages)`

### `tools/__init__.py` — 1 lines / 39 bytes

---

# 45. Non-Python project assets to know about

## Primary snapshot

The supplied primary archive contains source, tests and scripts but no root `pyproject.toml`, `requirements.txt`, `.env.example`, or bundled Piper asset tree.

## David snapshot

Important non-Python assets include:

```text
.env.example
.gitignore
README.md
pyproject.toml
requirements.txt
assets/models/en_US-lessac-medium.onnx
assets/models/en_US-lessac-medium.onnx.json
assets/piper/piper.exe
assets/piper/*.dll
assets/piper/espeak-ng-data/*
ADVI_folders.zip
```

The exact contents of these large bundled runtime assets should not be duplicated unless the unified packaging/runtime actually needs them.

---

# 46. Development philosophy to preserve

The supplied memory documentation is unusually valuable because it records why complexity was rejected.

Preserve these principles:

- Correctness before cleverness.
- Measure performance before optimizing.
- Keep short-term context bounded.
- Use evidence retrieval plus LLM reasoning rather than letting a retriever answer blindly.
- Avoid unnecessary infrastructure.
- Lazy-load expensive semantic models.
- Keep provider-specific API details behind provider abstractions.
- Keep execution reality in deterministic code.
- Keep user-facing response generation with the conversational intelligence layer rather than scattered local formatters.

The engineering history explicitly says that when behavior is wrong, the useful debugging method is to isolate the failing layer before changing architecture. [Source: ADVI Technical Documentation — Part 3 of 3, Debugging Philosophy]

---

# 47. Final mental model

When modifying ADVI, think in these layers:

```text
                    USER
                      │
                      ▼
             ┌─────────────────┐
             │  CONVERSATION   │
             │ context/memory  │
             └────────┬────────┘
                      │
                      ▼
             ┌─────────────────┐
             │      BRAIN      │
             │ understand      │
             │ reason          │
             │ plan            │
             └────────┬────────┘
                      │
                      ▼
             ┌─────────────────┐
             │   CAPABILITIES  │
             │ Gmail / Files   │
             │ Desktop / GUI   │
             │ Browser / Apps  │
             └────────┬────────┘
                      │
                      ▼
             ┌─────────────────┐
             │    EXECUTION    │
             │ actual computer │
             │ actual services │
             └────────┬────────┘
                      │
                      ▼
             ┌─────────────────┐
             │  VERIFICATION   │
             │ did it work?    │
             └────────┬────────┘
                      │
                      ▼
             RESULT / CONTEXT / USER
```

The purpose of the architecture is to make this flow **simple enough to understand, powerful enough to act, and trustworthy enough to tell the truth about what happened.**

---

# 48. Document maintenance rule

After a major architectural change, update at minimum:

```text
1. runtime/entry point
2. directory map
3. major component responsibilities
4. data flow
5. provider/model flow
6. memory flow
7. task/execution flow
8. fallback/desktop execution flow
9. known limitations
10. symbol inventory if files/classes/functions changed substantially
```

Do not allow this document to become a historical essay that no longer matches the code. It should remain a practical navigation map for the next engineer or AI agent.
