from __future__ import annotations

from advi.core.structured_output import parse_structured_output

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .intent import Intent, IntentType
from .pipeline_trace import (
    intent_to_dict,
    next_llm_call_id,
    plan_to_dict as trace_plan_to_dict,
    trace,
    trace_exception,
)


class PlanStatus(str, Enum):
    READY = "ready"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass(frozen=True)
class PlanStep:
    action: str
    parameters: dict[str, str] = field(
        default_factory=dict
    )
    reason: str = ""
    original_input: str = ""


@dataclass(frozen=True)
class Plan:
    goal: str
    confidence: float
    steps: list[PlanStep] = field(
        default_factory=list
    )
    status: PlanStatus = PlanStatus.READY

    def __post_init__(self) -> None:
        confidence = max(
            0.0,
            min(1.0, float(self.confidence)),
        )

        object.__setattr__(
            self,
            "confidence",
            confidence,
        )


def plan_to_dict(
    plan: Plan,
) -> dict[str, Any]:
    return {
        "goal": plan.goal,
        "confidence": round(
            plan.confidence,
            2,
        ),
        "status": plan.status.value,
        "steps": [
            {
                "action": step.action,
                "parameters": step.parameters,
                "reason": step.reason,
            }
            for step in plan.steps
        ],
    }


def plan_to_json(
    plan: Plan,
) -> str:
    return json.dumps(
        plan_to_dict(plan),
        ensure_ascii=False,
        separators=(",", ":"),
    )


class Planner:
    """
    LLM-backed planner.

    Gemini decides what steps are required.
    Python validates and materializes the resulting Plan.
    """

    PLAN_SCHEMA: dict[str, Any] = {
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
            },
            "confidence": {
                "type": "number",
            },
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": [
                                "memory_retrieval",
                                "memory_update",
                                "memory_forget",
                                "capability_query",
                                "identity_query",
                                "conversation",
                                "email_draft_create",
                                "email_draft_read",
                                "email_draft_update",
                                "email_send",
                                "open_application",
                                "close_window",
                                "focus_window",
                                "type_text",
                                "press_key",
                                "hotkey",
                                "click",
                                "double_click",
                                "right_click",
                                "scroll",
                                "wait",
                                "finish",
                                "navigate",
                                "search",
                                "save_file",
                                "create_file",
                                "read_file",
                                "delete_file",
                            ],
                        },
                        "parameters": {
                            "type": "object",
                            "additionalProperties": {
                                "type": "string",
                            },
                        },
                        "reason": {
                            "type": "string",
                        },
                    },
                    "required": [
                        "action",
                        "parameters",
                        "reason",
                    ],
                },
            },
        },
        "required": [
            "goal",
            "confidence",
            "steps",
        ],
    }


    NEXT_STEP_SCHEMA: dict[str, Any] = {
        "type": "object",
        "properties": {
            "decision": {
                "type": "string",
                "enum": [
                    "next_step",
                    "done",
                    "await_user",
                ],
            },
            "reason": {
                "type": "string",
            },
            "step": {
                "type": [
                    "object",
                    "null",
                ],
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "memory_retrieval",
                            "memory_update",
                            "memory_forget",
                            "capability_query",
                            "identity_query",
                            "conversation",
                            "email_draft_create",
                            "email_draft_read",
                            "email_draft_update",
                            "email_send",
                            "open_application",
                            "close_window",
                            "focus_window",
                            "type_text",
                            "press_key",
                            "hotkey",
                            "click",
                            "double_click",
                            "right_click",
                            "scroll",
                            "wait",
                            "finish",
                            "navigate",
                            "search",
                            "save_file",
                            "create_file",
                            "read_file",
                            "delete_file",
                        ],
                    },
                    "parameters": {
                        "type": "object",
                        "additionalProperties": {
                            "type": "string",
                        },
                    },
                    "reason": {
                        "type": "string",
                    },
                },
                "required": [
                    "action",
                    "parameters",
                    "reason",
                ],
            },
        },
        "required": [
            "decision",
            "reason",
            "step",
        ],
    }

    def __init__(
        self,
        provider=None,
    ) -> None:
        self.provider = provider

    def create_plan(
        self,
        intent: Intent,
        current_task_context: str = "",
    ) -> Plan:
        """
        Create a complete plan from the recognized intent.

        When an LLM provider is available, Gemini creates the plan.
        A deterministic fallback remains only for tests or a runtime
        where no planning provider is configured.
        """
        trace(
            "Planner.ENTER",
            source_component="Planner",
            input_intent=intent_to_dict(intent),
            current_task_context=current_task_context,
            provider=(
                getattr(self.provider, "name", type(self.provider).__name__)
                if self.provider is not None
                else None
            ),
        )

        if self.provider is None:
            plan = self._fallback_plan(
                intent
            )
        else:
            plan = self._llm_plan(
                intent,
                current_task_context,
            )

        trace(
            "Planner.EXIT",
            source_component="Planner",
            parsed_plan=trace_plan_to_dict(plan),
        )
        return plan

    def decide_next_step(
        self,
        intent: Intent,
        task_context: str,
        executed_step: PlanStep,
        execution_result: Any,
    ) -> dict[str, Any]:
        """
        Ask Gemini what should happen after one executed step.

        Returns:
            {
                "decision": "next_step" | "done" | "await_user",
                "reason": "...",
                "step": PlanStep | None,
            }
        """

        result_json = json.dumps(
            execution_result,
            ensure_ascii=False,
            default=str,
        )

        prompt = f"""
You are ADVI's execution planner.

You are continuing an active task one step at a time.

The previous step has ALREADY been executed by Python.

You must now decide what happens next.

RULES:

1. Trust the Python execution result as authoritative.
2. Never claim that an action succeeded unless the result says
   success=true.
3. If the task is complete, return "done".
4. If the user must make a decision or confirmation is required,
   return "await_user".
5. Otherwise return exactly ONE next executable step.
6. Do not repeat a successfully completed step unless the result
   clearly shows that it needs to be retried.
7. Never invent IDs, recipients, addresses, or values.
8. Never create email_send automatically after email_draft_create.
9. Email sending requires explicit user confirmation.
10. Use the existing task context to resolve references.

USER INTENT:

intent = {intent.type.value}
original_input = {intent.original_input}
entities = {json.dumps(intent.entities, ensure_ascii=False)}
parameters = {json.dumps(intent.parameters, ensure_ascii=False)}

CURRENT TASK:

{task_context}

JUST EXECUTED STEP:

action = {executed_step.action}
parameters = {json.dumps(executed_step.parameters, ensure_ascii=False)}

AUTHORITATIVE PYTHON RESULT:

{result_json}

Return the next decision.
""".strip()

        messages = [
            {
                "role": "system",
                "content": (
                    "You are ADVI's execution planning component. "
                    "Return only the requested structured decision."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]

        if self.provider is None:
            return {
                "decision": "done",
                "reason": (
                    "No planning provider is configured; "
                    "compatibility execution stops after this step."
                ),
                "step": None,
            }

        structured = getattr(
            self.provider,
            "structured",
            None,
        )

        if callable(structured):
            llm_call_id = next_llm_call_id()
            trace(
                "Planner.provider_request",
                provider=getattr(self.provider, "name", type(self.provider).__name__),
                model=getattr(self.provider, "model", None),
                purpose="plan_creation",
                llm_call_id=llm_call_id,
                messages=messages,
            )
            response = structured(
                messages,
                schema=self.NEXT_STEP_SCHEMA,
            )
        else:
            llm_call_id = next_llm_call_id()
            trace(
                "Planner.provider_request",
                provider=getattr(self.provider, "name", type(self.provider).__name__),
                model=getattr(self.provider, "model", None),
                purpose="next_step_decision",
                llm_call_id=llm_call_id,
                messages=messages,
            )
            response = self.provider.chat(
                messages
            )

        decision = self._parse_next_step(
            response.text
        )
        trace(
            "Planner.parsed_plan",
            purpose="next_step_decision",
            llm_call_id=llm_call_id,
            decision=decision,
        )
        return decision

    @staticmethod
    def _parse_next_step(
        text: str,
    ) -> dict[str, Any]:
        try:
            data = parse_structured_output(text, Planner.NEXT_STEP_SCHEMA).data
        except ValueError:
            return {
                "decision": "done",
                "reason": "Planner returned invalid JSON.",
                "step": None,
            }

        decision = str(
            data.get(
                "decision",
                "done",
            )
        ).strip().lower()

        if decision not in {
            "next_step",
            "done",
            "await_user",
        }:
            decision = "done"

        raw_step = data.get("step")

        if (
            decision != "next_step"
            or not isinstance(
                raw_step,
                dict,
            )
        ):
            return {
                "decision": decision,
                "reason": str(
                    data.get(
                        "reason",
                        "",
                    )
                ).strip(),
                "step": None,
            }

        action = str(
            raw_step.get(
                "action",
                "",
            )
        ).strip()

        parameters = raw_step.get(
            "parameters",
            {},
        )

        if not isinstance(
            parameters,
            dict,
        ):
            parameters = {}

        parameters = {
            str(key): str(value)
            for key, value in parameters.items()
            if value is not None
        }

        step = PlanStep(
            action=action,
            parameters=parameters,
            reason=str(
                raw_step.get(
                    "reason",
                    "",
                )
            ).strip(),
        )

        return {
            "decision": "next_step",
            "reason": str(
                data.get(
                    "reason",
                    "",
                )
            ).strip(),
            "step": step,
        }   


    def _llm_plan(
        self,
        intent: Intent,
        current_task_context: str,
    ) -> Plan:
        trace(
            "Planner._llm_plan.ENTER",
            source_component="Planner",
            input_intent=intent_to_dict(intent),
            current_task_context=current_task_context,
            provider=getattr(
                self.provider,
                "name",
                type(self.provider).__name__,
            ),
        )

        prompt = f"""
You are ADVI's task planner.

Your job is to convert the recognized user intent into the
smallest correct execution plan.

The plan may contain ONE or MULTIPLE steps.

Important principles:

1. Do not perform actions yourself.
2. Create actions that Python/ADVI can execute.
3. Use the recognized intent as the primary source of what
   the user wants.
4. Preserve explicitly extracted parameters.
5. Do not invent recipients, email addresses, IDs, or values.
6. Do not create unnecessary steps.
7. A simple task should normally have one step.
8. A genuinely compound request may have multiple steps.
9. `email_send` is a consequential action. Do not add it
   automatically after `email_draft_create`; sending must remain
   a separate confirmation-controlled action.
10. For an existing task, respect the current task context.

Recognized intent:

intent = {intent.type.value}
confidence = {intent.confidence}
target = {intent.target}
entities = {json.dumps(intent.entities, ensure_ascii=False)}
parameters = {json.dumps(intent.parameters, ensure_ascii=False)}

Original user input:

{intent.original_input}

Current task context:

{current_task_context or "No active task."}

Return the complete execution plan.
""".strip()

        messages = [
            {
                "role": "system",
                "content": (
                    "You are ADVI's planning component. "
                    "Return only the structured plan requested."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]

        structured = getattr(
            self.provider,
            "structured",
            None,
        )

        llm_call_id = next_llm_call_id()

        if callable(structured):
            trace(
                "Planner.provider_request",
                provider=getattr(
                    self.provider,
                    "name",
                    type(self.provider).__name__,
                ),
                model=getattr(
                    self.provider,
                    "model",
                    None,
                ),
                purpose="plan_creation",
                llm_call_id=llm_call_id,
                mode="structured",
                messages=messages,
                schema=self.PLAN_SCHEMA,
            )

            response = structured(
                messages,
                schema=self.PLAN_SCHEMA,
            )
        else:
            trace(
                "Planner.provider_request",
                provider=getattr(
                    self.provider,
                    "name",
                    type(self.provider).__name__,
                ),
                model=getattr(
                    self.provider,
                    "model",
                    None,
                ),
                purpose="plan_creation",
                llm_call_id=llm_call_id,
                mode="chat",
                messages=messages,
            )

            response = self.provider.chat(
                messages
            )

        trace(
            "Planner.provider_response",
            provider=getattr(
                self.provider,
                "name",
                type(self.provider).__name__,
            ),
            model=getattr(
                self.provider,
                "model",
                None,
            ),
            purpose="plan_creation",
            llm_call_id=llm_call_id,
            response_text=getattr(
                response,
                "text",
                None,
            ),
        )

        try:
            trace(
                "Planner.parse_start",
                llm_call_id=llm_call_id,
                response_text=getattr(
                    response,
                    "text",
                    None,
                ),
            )

            plan = self._parse_plan(
                response.text,
                intent,
            )

            trace(
                "Planner.parse_success",
                llm_call_id=llm_call_id,
                parsed_plan=trace_plan_to_dict(plan),
            )

            trace(
                "Planner._llm_plan.EXIT",
                source_component="Planner",
                llm_call_id=llm_call_id,
                parsed_plan=trace_plan_to_dict(plan),
            )

            return plan

        except Exception as exc:
            trace_exception(
                "Planner.parse_exception",
                exc,
                llm_call_id=llm_call_id,
                response_text=getattr(
                    response,
                    "text",
                    None,
                ),
                intent=intent_to_dict(intent),
            )
            raise


        

    @classmethod
    def _parse_plan(
        cls,
        text: str,
        intent: Intent,
    ) -> Plan:
        try:
            data = parse_structured_output(text, cls.PLAN_SCHEMA).data
        except ValueError:
            return Plan(
                goal="unknown",
                confidence=0.0,
                status=PlanStatus.FAILED,
            )

        goal = str(
            data.get(
                "goal",
                "",
            )
        ).strip()

        try:
            confidence = float(
                data.get(
                    "confidence",
                    intent.confidence,
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            confidence = intent.confidence

        raw_steps = data.get(
            "steps",
            [],
        )

        if not isinstance(
            raw_steps,
            list,
        ):
            return Plan(
                goal=goal or "unknown",
                confidence=confidence,
                status=PlanStatus.FAILED,
            )

        steps: list[PlanStep] = []

        allowed_actions = {
            "memory_retrieval",
            "memory_update",
            "memory_forget",
            "capability_query",
            "identity_query",
            "conversation",
            "email_draft_create",
            "email_draft_read",
            "email_draft_update",
            "email_send",
        }

        for raw_step in raw_steps:
            if not isinstance(
                raw_step,
                dict,
            ):
                continue

            action = str(
                raw_step.get(
                    "action",
                    "",
                )
            ).strip()

            if action not in allowed_actions:
                continue

            raw_parameters = raw_step.get(
                "parameters",
                {},
            )

            if not isinstance(
                raw_parameters,
                dict,
            ):
                raw_parameters = {}

            parameters = {
                str(key): str(value)
                for key, value in raw_parameters.items()
                if value is not None
            }

            reason = str(
                raw_step.get(
                    "reason",
                    "",
                )
            ).strip()

            # Preserve original intent fields when Gemini
            # accidentally omits explicitly extracted values.
            if action == "email_draft_create":
                for key in (
                    "recipient",
                    "subject",
                    "body",
                    "draft_id",
                ):
                    if (
                        key not in parameters
                        and key in intent.entities
                        and intent.entities[key]
                    ):
                        parameters[key] = (
                            intent.entities[key]
                        )

            steps.append(
                PlanStep(
                    action=action,
                    parameters=parameters,
                    reason=reason,
                    original_input=intent.original_input,
                )
            )

        if not steps:
            return Plan(
                goal=goal or "unknown",
                confidence=confidence,
                status=PlanStatus.BLOCKED,
            )

        return Plan(
            goal=goal or steps[0].action,
            confidence=confidence,
            steps=steps,
            status=PlanStatus.READY,
        )

    @staticmethod
    def _fallback_plan(
        intent: Intent,
    ) -> Plan:
        """
        Compatibility fallback for tests/offline operation.

        Runtime should normally use the LLM-backed path.
        """
        intent_to_action = {
            IntentType.MEMORY_RETRIEVAL: "memory_retrieval",
            IntentType.MEMORY_UPDATE: "memory_update",
            IntentType.MEMORY_FORGET: "memory_forget",
            IntentType.CAPABILITY_QUERY: "capability_query",
            IntentType.IDENTITY_QUERY: "identity_query",
            IntentType.CONVERSATION: "conversation",
            IntentType.EMAIL_DRAFT_CREATE: "email_draft_create",
            IntentType.EMAIL_READ: "email_draft_read",
            IntentType.EMAIL_DRAFT_UPDATE: "email_draft_update",
            IntentType.EMAIL_SEND: "email_send",
        }

        action = intent_to_action.get(
            intent.type
        )

        if action is None:
            return Plan(
                goal="unknown",
                confidence=intent.confidence,
                status=PlanStatus.BLOCKED,
            )

        parameters = dict(
            intent.parameters
        )

        if intent.target:
            parameters.setdefault(
                "target",
                intent.target,
            )

        for key in (
            "recipient",
            "subject",
            "body",
            "message_id",
            "draft_id",
        ):
            value = intent.entities.get(key)

            if value:
                parameters[key] = value

        return Plan(
            goal=action,
            confidence=intent.confidence,
            steps=[
                PlanStep(
                    action=action,
                    parameters=parameters,
                    reason=(
                        "Compatibility fallback for "
                        f"{intent.type.value}"
                    ),
                    original_input=intent.original_input,
                )
            ],
        )
