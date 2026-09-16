# from markdown_it.helpers import parse_link_destination
from __future__ import annotations

from advi.core.structured_output import parse_structured_output, StructuredOutputError

import json
import logging
from typing import Any

from ..providers import LLMProvider
from .intent import Intent, IntentType
from .llm_telemetry import LLMTelemetry
from .pipeline_trace import (
    intent_to_dict,
    next_llm_call_id,
    trace,
    trace_exception,
)
from .task import Task


logger = logging.getLogger(__name__)


class IntentDetector:
    """Detect the user's primary intent using an LLM."""

    def __init__(
        self,
        provider: LLMProvider,
        telemetry: LLMTelemetry | None = None
    ) -> None:
        self.provider = provider
        self.telemetry = telemetry
        self._current_task: Task | None = None

    def _build_task_context(self) -> str:
        task = self._current_task

        if task is None:
            return "There is no active task."

        lines = [
            "CURRENT ACTIVE TASK:",
            f"- task_id: {task.task_id}",
            f"- status: {task.status.value}",
        ]

        if task.steps:
            step_index = min(
                max(task.current_step, 0),
                len(task.steps) - 1,
            )

            step = task.steps[step_index]

            lines.extend(
                [
                    f"- current_step: {step_index + 1}",
                    f"- total_steps: {len(task.steps)}",
                    f"- current_action: {step.action}",
                ]
            )

            if step.parameters:
                lines.append(
                    "- current_step_parameters:"
                )

                for key, value in step.parameters.items():
                    lines.append(
                        f"  - {key}: {value}"
                    )

        if task.confirmation is not None:
            lines.extend(
                [
                    "- awaiting_confirmation: true",
                    (
                        "- confirmation_action: "
                        f"{task.confirmation.action}"
                    ),
                    (
                        "- confirmation_summary: "
                        f"{task.confirmation.summary}"
                    ),
                ]
            )
        else:
            lines.append(
                "- awaiting_confirmation: false"
            )

        task_context = getattr(
            task,
            "context",
            {},
        )

        if task_context:
            lines.append(
                "- current_task_context:"
            )

            important_keys = (
                "gmail_draft_id",
                "email_recipient",
                "email_subject",
                "email_body",
                "recipient_name",
                "waiting_for",
            )

            for key in important_keys:
                value = task_context.get(key)

                if value:
                    lines.append(
                        f"  - {key}: {value}"
                    )

        return "\n".join(lines)    

    def set_current_task(
        self,
        task: Task | None,
    ) -> None:
        self._current_task = task

    INTENT_SCHEMA: dict[str, Any] = {
        "type": "object",
        "properties": {
            "intent": {
                "type": "string",
                "enum": [
                    "conversation",
                    "memory_retrieval",
                    "memory_update",
                    "memory_forget",
                    "capability_query",
                    "identity_query",
                    "information_request",
                    "system_control",
                    "task_confirmation",
                    "task_rejection",
                    "task_modification",
                    "task_pause",
                    "task_resume",
                    "task_cancel",
                    "task_readback",
                    "email_draft_create",
                    "email_read",
                    "email_draft_update",
                    "email_send",
                    "unknown",
                ],
                "description": (
                    "The single primary ADVI intent."
                ),
            },
            "confidence": {
                "type": "number",
                "description": (
                    "Confidence from 0.0 to 1.0."
                ),
            },
            "target": {
                "type": [
                    "string",
                    "null",
                ],
                "description": (
                    "Stable target or memory key when applicable."
                ),
            },
            "entities": {
                "type": "object",
                "properties": {
                    "recipient": {
                        "type": [
                            "string",
                            "null",
                        ],
                        "description": (
                            "Email recipient name or email address."
                        ),
                    },
                    "subject": {
                        "type": [
                            "string",
                            "null",
                        ],
                        "description": (
                            "Email subject when explicitly provided."
                        ),
                    },
                    "body": {
                        "type": [
                            "string",
                            "null",
                        ],
                        "description": (
                            "Email body or requested message content."
                        ),
                    },
                    "style": {
                        "type": [
                            "string",
                            "null",
                        ],
                        "description": (
                            "Requested writing style, tone, or formality."
                        ),
                    },
                    "message_id": {
                        "type": [
                            "string",
                            "null",
                        ],
                        "description": (
                            "Existing Gmail message ID when applicable."
                        ),
                    },
                    "draft_id": {
                        "type": [
                            "string",
                            "null",
                        ],
                        "description": (
                            "Existing Gmail draft ID when applicable."
                        ),
                    },
                    "field": {
                        "type": [
                            "string",
                            "null",
                        ],
                        "description": (
                            "Field the user wants to modify."
                        ),
                    },
                    "value": {
                        "type": [
                            "string",
                            "null",
                        ],
                        "description": (
                            "New value requested for a modified field."
                        ),
                    },
                    "relationship": {
                        "type": [
                            "string",
                            "null",
                        ],
                        "description": (
                            "Relationship to the user when relevant."
                        ),
                    },
                    "property": {
                        "type": [
                            "string",
                            "null",
                        ],
                        "description": (
                            "Memory property when relevant."
                        ),
                    },
                },
                "required": [
                    "recipient",
                    "subject",
                    "body",
                    "style",
                    "message_id",
                    "draft_id",
                    "field",
                    "value",
                    "relationship",
                    "property",
                ],
            },
            "parameters": {
                "type": "object",
                "properties": {
                    "recipient": {
                        "type": [
                            "string",
                            "null",
                        ],
                    },
                    "subject": {
                        "type": [
                            "string",
                            "null",
                        ],
                    },
                    "body": {
                        "type": [
                            "string",
                            "null",
                        ],
                    },
                    "draft_id": {
                        "type": [
                            "string",
                            "null",
                        ],
                    },
                    "message_id": {
                        "type": [
                            "string",
                            "null",
                        ],
                    },
                },
            },
        },
        "required": [
            "intent",
            "confidence",
            "target",
            "entities",
            "parameters",
        ],
    }    

    def detect(
        self,
        user_input: str,
    ) -> Intent:
        text = user_input.strip()
        task_context = self._build_task_context()

        trace(
            "IntentDetector.ENTER",
            source_component="IntentDetector",
            input_text=text,
            current_task=(
                self._current_task.task_id
                if self._current_task is not None
                else None
            ),
            task_status=(
                self._current_task.status.value
                if self._current_task is not None
                else None
            ),
        )

        if not text:
            return Intent(
                type=IntentType.UNKNOWN,
                confidence=1.0,
                original_input=text,
            )

        prompt = f"""
Classify the user's primary intent.

Allowed intents are enforced by the response schema.

Core rules:

1. Choose exactly ONE primary intent.
2. Use the current task context when it exists.
3. Do not invent entities, recipients, addresses, or values.
4. Extract explicit information from the user's message.
5. Do not answer the user's question.
6. Confidence must reflect actual certainty.

Intent guidance:

- conversation:
  Normal conversation or casual interaction.

- information_request:
  Factual questions or explanations that do not primarily
  concern ADVI's memory, capabilities, or identity.

- memory_retrieval:
  The user asks for something ADVI may already remember
  about the user.

- memory_update:
  The user asks ADVI to remember or update persistent information.

- memory_forget:
  The user asks ADVI to forget persistent information.

- capability_query:
  The user asks what ADVI can or cannot do.

- identity_query:
  The user asks who or what ADVI is.

- system_control:
  The user wants computer/system control.

Task-context rules:

When a current task exists, interpret short or ambiguous
messages relative to that task.

If the current task is awaiting confirmation:
- approval such as "yes", "send it", "go ahead" -> task_confirmation
- rejection such as "no", "cancel it" -> task_rejection
- "read it again" -> task_readback
- "make it shorter", "change the subject", etc. -> task_modification
- "pause this" -> task_pause
- "resume it" -> task_resume
- "cancel the whole thing" -> task_cancel

Important:
When an existing task is awaiting confirmation, "send it"
means task_confirmation, not email_send.

Current-task resolution rules:

When the user refers to:
- "it"
- "this"
- "that"
- "the email"
- "the draft"
- "the message"

resolve the reference using CURRENT ACTIVE TASK and its
current step/context.

For an awaiting email confirmation:
- "yes"
- "yes, send it"
- "send it"
- "go ahead"
- "do it"

mean task_confirmation when the current confirmation_action
is email_send.

Do not reinterpret an approval as a new email_send request.

If the user asks to change the draft instead, use
task_modification and identify the requested field/value.

Example of active-task interpretation:

CURRENT ACTIVE TASK:
- status: awaiting_confirmation
- current_action: email_draft_create
- confirmation_action: email_send
- email_recipient: joelpaulson105@gmail.com
- email_subject: Happy Birthday
- email_body: Dear Joel, ...

USER:
"yes, send it"

RETURN:
{{
  "intent": "task_confirmation",
  "confidence": 0.99,
  ...
}}

Do NOT return:
{{
  "intent": "email_send"
}}

Email rules:

- email_draft_create:
  User wants an email composed/prepared.
  Extract recipient, subject, and body when explicitly present.

- email_read:
  User wants an email read/retrieved.

- email_draft_update:
  User wants an existing draft modified.

- email_send:
  Represents the underlying consequential send action.
  Do not use it merely because the user says "send".
  If a current task is awaiting confirmation, approval belongs
  to task_confirmation.

For email_draft_create:

Extract every explicitly stated email detail into entities.

Use:
- recipient for the person name or email address
- subject for an explicitly stated subject
- body for the requested message content
- style for requested tone/formality

Use null for fields that are not provided.

Example:
User: "Write an email to Joel saying good morning happy birthday."
Return:
entities.recipient = "Joel"
entities.body = "good morning happy birthday"
entities.subject = null
entities.style = null

Current task context:
{task_context}

User input:
{text}
""".strip()

        try:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are ADVI's intent classification "
                        "component. Return the requested "
                        "structured intent only."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ]

            provider_name = getattr(
                self.provider,
                "name",
                type(self.provider).__name__,
            )
            provider_model = getattr(
                self.provider,
                "model",
                None,
            )

            trace(
                "intent.context",
                source_component="IntentDetector",
                context_source_task_manager=task_context,
                input_text=text,
                final_messages=messages,
                system_prompt=messages[0]["content"],
                task_context=task_context,
                task_status=(
                    self._current_task.status.value
                    if self._current_task is not None
                    else None
                ),
            )

            trace(
                "intent_detector.request",
                provider=provider_name,
                model=provider_model,
                messages=messages,
                schema=self.INTENT_SCHEMA,
                task_context=task_context,
                input_text=text,
            )

            structured = getattr(
                self.provider,
                "structured",
                None,
            )

            llm_call_id = next_llm_call_id()

            trace(
                "IntentDetector.before_provider_call",
                provider=provider_name,
                model=provider_model,
                purpose="intent_detection",
                llm_call_id=llm_call_id,
                task_context=task_context,
            )

            if callable(structured):
                result = structured(
                    messages,
                    schema=self.INTENT_SCHEMA,
                )
            else:
                # Compatibility for lightweight test doubles
                # and legacy providers that only implement chat().
                result = self.provider.chat(messages)

            trace(
                "intent_detector.provider_response",
                llm_call_id=llm_call_id,
                raw_text=result.text,
                finish_reason=getattr(
                    result,
                    "finish_reason",
                    None,
                ),
                input_tokens=getattr(
                    result,
                    "input_tokens",
                    None,
                ),
                output_tokens=getattr(
                    result,
                    "output_tokens",
                    None,
                ),
                latency_ms=getattr(
                    result,
                    "latency_ms",
                    None,
                ),
            )

            if getattr(result, "finish_reason", None) == "MAX_TOKENS":
                trace(
                    "intent_detector.truncated",
                    finish_reason="MAX_TOKENS",
                    raw_text=result.text,
                )

            if self.telemetry is not None:
                self.telemetry.record(
                    result,
                    "intent_detection",
                )

            parsed = self._parse(
                result.text,
                text,
            )

            trace(
                "intent.return",
                source_component="IntentDetector",
                intent=intent_to_dict(parsed),
            )

            trace(
                "IntentDetector.EXIT",
                source_component="IntentDetector",
                parsed_intent=intent_to_dict(parsed),
            )

            return parsed

        except Exception as exc:
            trace_exception(
                "intent_detector.error",
                exc,
                input_text=text,
            )

            return Intent(
                type=IntentType.UNKNOWN,
                confidence=0.0,
                original_input=text,
            )

            return Intent(
                type=IntentType.UNKNOWN,
                confidence=0.0,
                original_input=text,
            )

    @staticmethod
    def _parse(
        text: str,
        original_input: str,
    ) -> Intent:
        trace(
            "intent.parse.input",
            raw_text=text,
            original_input=original_input,
        )

        try:
            parsed = parse_structured_output(text, IntentDetector.INTENT_SCHEMA)
            data = parsed.data
            if parsed.repaired:
                trace("intent.parse.repaired", raw_text=text, parsed_dict=data)
        except StructuredOutputError as exc:
            trace_exception(
                "intent.parse.error",
                exc,
                raw_text=text,
            )

            return Intent(
                type=IntentType.UNKNOWN,
                confidence=0.0,
                original_input=original_input,
            )

        trace(
            "intent.parse.dict",
            parsed_dict=data,
        )

        raw_intent = str(
            data.get("intent", "unknown")
        ).strip().lower()

        try:
            intent_type = IntentType(raw_intent)
        except ValueError:
            intent_type = IntentType.UNKNOWN

        try:
            confidence = float(
                data.get("confidence", 0.0)
            )
        except (TypeError, ValueError):
            confidence = 0.0

        target = data.get("target")

        if target is not None:
            target = str(target).strip() or None

        entities = data.get(
            "entities",
            {},
        )

        if not isinstance(entities, dict):
            entities = {}

        entities = {
            str(key): str(value)
            for key, value in entities.items()
            if value is not None
        }

        parameters = data.get(
            "parameters",
            {},
        )

        if not isinstance(parameters, dict):
            parameters = {}

        parameters = {
            str(key): str(value)
            for key, value in parameters.items()
            if value is not None
        }

        intent = Intent(
            type=intent_type,
            confidence=confidence,
            original_input=original_input,
            target=target,
            entities=entities,
            parameters=parameters,
        )

        trace(
            "intent.parse.output",
            type=intent.type.value,
            confidence=intent.confidence,
            target=intent.target,
            entities=intent.entities,
            parameters=intent.parameters,
            original_input=intent.original_input,
        )

        return intent
