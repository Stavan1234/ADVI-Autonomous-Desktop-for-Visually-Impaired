# from huggingface_hub.inference._generated.types import zero_shot_image_classification
# from huggingface_hub.inference._generated.types import zero_shot_image_classification
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from .executor import ExecutionResult, Executor
from .intent import Intent, IntentType
from .pipeline_trace import (
    execution_result_to_dict,
    intent_to_dict,
    plan_to_dict as trace_plan_to_dict,
    set_task_id,
    task_to_dict,
    trace,
)
from .planner import Plan, PlanStep, Planner, PlanStatus
from .task import Task, TaskStatus
from .task_manager import TaskManager


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TaskExecution:
    plan: Plan
    results: list[ExecutionResult]
    task: Task | None = None


class TaskCoordinator:
    """Coordinate intent planning and safe execution."""

    @property
    def current_task(self) -> Task | None:
        return self.task_manager.current_task()

    def __init__(
        self,
        planner: Planner | None = None,
        executor: Executor | None = None,
        task_manager: TaskManager | None = None,
    ) -> None:
        self.planner = planner or Planner()
        self.executor = executor or Executor()
        self.task_manager = task_manager or TaskManager()

    def handle_task_intent(self, intent):
        task = self.current_task

        trace(
            "TaskCoordinator.handle_task_intent.ENTER",
            source_component="TaskCoordinator",
            incoming_intent=intent_to_dict(intent),
            current_task=task_to_dict(task) if task else None,
            confirmation=(
                task.confirmation
                if task is not None
                else None
            ),
            draft_id=(
                task.context.get("gmail_draft_id")
                if task is not None
                else None
            ),
        )

        trace(
            "task_coordinator.handle_task_intent",
            source_component="TaskCoordinator",
            decision="evaluate_task_intent",
            incoming_intent=intent_to_dict(intent),
            current_task=task_to_dict(task) if task else None,
        )

        if task is None:
            trace(
                "task_coordinator.handle_task_intent",
                decision="NOOP",
                reason="no_current_task",
            )
            return None

        if intent.type == IntentType.TASK_CONFIRMATION:
            trace(
                "task_coordinator.decision",
                decision="TASK_CONFIRMATION",
                task_id=task.task_id,
            )
            confirmation = task.confirmation

            if (
                confirmation is not None
                and confirmation.action
                == "email_send"
            ):
                draft_id = task.context.get(
                    "gmail_draft_id"
                )

                if not draft_id:
                    trace(
                        "task_coordinator.decision",
                        decision="EMAIL_SEND_BLOCKED",
                        task_id=task.task_id,
                        reason="missing_gmail_draft_id",
                    )
                    return None

                send_step = PlanStep(
                    action="email_send",
                    parameters={
                        "draft_id": draft_id,
                    },
                    reason="Confirmed email send.",
                    original_input="User confirmed email send.",
                )

                trace(
                    "task_coordinator.execute_confirmation",
                    decision="EXECUTE_EMAIL_SEND",
                    task_id=task.task_id,
                    step=(
                        {
                            "action": send_step.action,
                            "parameters": send_step.parameters,
                        }
                    ),
                )

                result = self.executor.execute(
                    send_step
                )

                trace(
                    "task_coordinator.confirmation_result",
                    task_id=task.task_id,
                    execution_result=execution_result_to_dict(
                        result
                    ),
                )
                trace(
                    "TaskCoordinator.handle_task_intent.EXIT",
                    source_component="TaskCoordinator",
                    branch="email_send_confirmation",
                    execution_result=execution_result_to_dict(result),
                )

                self.task_manager.update_context(
                    task.task_id,
                    {
                        "email_send_result": str(
                            result.data
                            if result.success
                            else result.error
                        ),
                    },
                )

                if result.success:
                    self.task_manager.approve(
                        task.task_id
                    )

                    trace(
                        "task_coordinator.decision",
                        decision="EMAIL_SEND_COMPLETED",
                        task_id=task.task_id,
                    )
                else:
                    trace(
                        "task_coordinator.decision",
                        decision="EMAIL_SEND_FAILED",
                        task_id=task.task_id,
                        error=result.error,
                    )

                return result

            return self.task_manager.approve(
                task.task_id
            )

        if intent.type == IntentType.TASK_REJECTION:
            trace(
                "task_coordinator.decision",
                decision="TASK_REJECTION",
                task_id=task.task_id,
            )
            return self.task_manager.reject(task.task_id)

        if intent.type == IntentType.TASK_PAUSE:
            trace(
                "task_coordinator.decision",
                decision="TASK_PAUSE",
                task_id=task.task_id,
            )
            return self.task_manager.pause(task.task_id)

        if intent.type == IntentType.TASK_RESUME:
            trace(
                "task_coordinator.decision",
                decision="TASK_RESUME",
                task_id=task.task_id,
            )
            resumed = self.task_manager.resume_last_paused()
            if resumed is not None:
                return resumed
            return self.task_manager.resume(task.task_id)

        if intent.type == IntentType.TASK_CANCEL:
            trace(
                "task_coordinator.decision",
                decision="TASK_CANCEL",
                task_id=task.task_id,
            )
            return self.task_manager.cancel(task.task_id)

        if intent.type == IntentType.TASK_READBACK:
            trace(
                "task_coordinator.decision",
                decision="TASK_READBACK",
                task_id=task.task_id,
            )
            return self.readback_current_task()

        if intent.type == IntentType.TASK_MODIFICATION:
            trace(
                "task_coordinator.decision",
                decision="TASK_MODIFICATION",
                task_id=task.task_id,
            )
            updates = {}

            if intent.target:
                value = intent.entities.get(
                    "value"
                )

                if value:
                    updates[
                        intent.target
                    ] = value

            for source_key, context_key in {
                "recipient": "email_recipient",
                "subject": "email_subject",
                "body": "email_body",
            }.items():
                value = intent.entities.get(
                    source_key
                )

                if value:
                    updates[context_key] = value

            if updates:
                return self.modify_current_task(
                    updates
                )

            return None

        return None

    def pause_current_task(self):
        trace(
            "task_coordinator.decision",
            decision="PAUSE_CURRENT_TASK",
            current_task=task_to_dict(self.current_task)
            if self.current_task
            else None,
        )
        return self.task_manager.pause_current()

    def resume_last_paused_task(self):
        return self.task_manager.resume_last_paused()


    @staticmethod
    def _normalize_email_recipient(
        recipient: str,
    ) -> str:
        """
        Convert a user/display recipient into the plain email address
        that must be passed to Gmail.

        Examples:
            "Joel (joelpaulson105@gmail.com)"
                -> "joelpaulson105@gmail.com"

            "joelpaulson105@gmail.com"
                -> "joelpaulson105@gmail.com"

            "Joel"
                -> "Joel"
        """
        import re

        value = (recipient or "").strip()

        if not value:
            return ""

        match = re.search(
            r"[\w.\-+%]+@[\w.\-]+\.[A-Za-z]{2,}",
            value,
        )

        if match:
            return match.group(0)

        return value    

    def modify_current_task(
        self,
        updates: dict[str, str],
    ):
        task = self.current_task

        if task is None:
            return None

        draft_id = task.context.get(
            "gmail_draft_id"
        )

        if draft_id:
            gmail = self.executor.gmail_service

            if gmail is None:
                return None

            recipient_display = updates.get(
                "email_recipient",
                task.context.get(
                    "email_recipient",
                    "",
                ),
            )

            recipient = self._normalize_email_recipient(
                recipient_display
            )

            subject = updates.get(
                "email_subject",
                task.context.get(
                    "email_subject",
                    "",
                ),
            )

            body = updates.get(
                "email_body",
                task.context.get(
                    "email_body",
                    "",
                ),
            )

            draft = gmail.update_draft(
                draft_id=draft_id,
                to=recipient,
                subject=subject,
                body=body,
            )

            self.task_manager.update_context(
                task.task_id,
                {
                    "email_recipient": (
                        draft.recipient
                    ),
                    "email_subject": (
                        draft.subject
                    ),
                    "email_body": (
                        draft.body
                    ),
                },
            )

            self.task_manager.await_confirmation(
                task.task_id,
                action="email_send",
                summary=(
                    f"Email to {draft.recipient}; "
                    f"subject: {draft.subject}"
                ),
            )

            return draft

        return self.task_manager.update_context(
            task.task_id,
            updates,
        )

    def get_current_task_context(self) -> dict[str, str]:
        task = self.current_task
        if task is None:
            return {}
        return dict(task.context)

    def readback_current_task(self):
        task = self.current_task

        if task is None:
            return None

        draft_id = task.context.get(
            "gmail_draft_id"
        )

        if not draft_id:
            return None

        if self.executor.gmail_service is None:
            return None

        return self.executor.gmail_service.get_draft(
            draft_id
        )

    def resolve_email_recipient(
        self,
        recipient_name: str,
    ) -> str | None:
        name = recipient_name.strip()

        if not name:
            return None

        memory = getattr(
            self.executor,
            "memory",
            None,
        )

        if memory is None:
            return None

        # ---------------------------------------------------------
        # Structured contact lookup is authoritative.
        # Do not use semantic memory to resolve email recipients.
        # ---------------------------------------------------------
        get_contact = getattr(
            memory,
            "get_contact",
            None,
        )

        if get_contact is not None:
            contact = get_contact(name)

            if contact is not None:
                trace(
                    "email.contact_resolution",
                    source_component="TaskCoordinator",
                    source="structured_contact",
                    requested_name=name,
                    resolved_email=contact.email,
                )
                return contact.email

        # Explicit address supplied by the user.
        if (
            "@" in name
            and "." in name.rsplit("@", 1)[-1]
        ):
            trace(
                "email.contact_resolution",
                source_component="TaskCoordinator",
                source="explicit_email",
                requested_name=name,
                resolved_email=name,
            )
            return name

        trace(
            "email.contact_resolution",
            source_component="TaskCoordinator",
            source="not_found",
            requested_name=name,
        )

        return None

    def missing_email_recipient(
        self,
        intent: Intent,
    ) -> str | None:
        if (
            intent.type
            != IntentType.EMAIL_DRAFT_CREATE
        ):
            return None

        recipient = intent.entities.get(
            "recipient"
        )

        if not recipient:
            return None

        if "@" in recipient:
            return None

        resolved = (
            self.resolve_email_recipient(
                recipient
            )
        )

        if resolved:
            return None

        return recipient

    # def _plan_for_intent(
    #     self,
    #     intent: Intent,
    # ) -> Plan:
    #     intent_to_action = {
    #         IntentType.MEMORY_RETRIEVAL: "memory_retrieval",
    #         IntentType.MEMORY_UPDATE: "memory_update",
    #         IntentType.MEMORY_FORGET: "memory_forget",
    #         IntentType.CAPABILITY_QUERY: "capability_query",
    #         IntentType.IDENTITY_QUERY: "identity_query",
    #         IntentType.CONVERSATION: "conversation",
    #         IntentType.EMAIL_DRAFT_CREATE: "email_draft_create",
    #         IntentType.EMAIL_READ: "email_read",
    #         IntentType.EMAIL_DRAFT_UPDATE: "email_draft_update",
    #         IntentType.EMAIL_SEND: "email_send",
    #     }

    #     action = intent_to_action.get(
    #         intent.type
    #     )

    #     if action is None:
    #         trace(
    #             "task_coordinator.plan",
    #             decision="BLOCKED",
    #             reason="unknown_intent",
    #             intent=intent_to_dict(intent),
    #         )

    #         return Plan(
    #             goal="unknown",
    #             confidence=intent.confidence,
    #             status=PlanStatus.BLOCKED,
    #         )

    #     parameters = dict(
    #         intent.parameters
    #     )

    #     if intent.target:
    #         parameters.setdefault(
    #             "target",
    #             intent.target,
    #         )

    #     if intent.type in {
    #         IntentType.EMAIL_DRAFT_CREATE,
    #         IntentType.EMAIL_READ,
    #         IntentType.EMAIL_DRAFT_UPDATE,
    #         IntentType.EMAIL_SEND,
    #     }:
    #         for key in (
    #             "recipient",
    #             "subject",
    #             "body",
    #             "message_id",
    #             "draft_id",
    #         ):
    #             value = intent.entities.get(key)

    #             if value:
    #                 parameters[key] = value

    #     return Plan(
    #         goal=action,
    #         confidence=intent.confidence,
    #         steps=[
    #             PlanStep(
    #                 action=action,
    #                 parameters=parameters,
    #                 reason=(
    #                     "Execute recognized intent: "
    #                     f"{intent.type.value}"
    #                 ),
    #                 original_input=intent.original_input,
    #             )
    #         ],
    #     )    

    def run(self, intent: Intent) -> TaskExecution:
        active_task = self.current_task

        trace(
            "TaskCoordinator.run.ENTER",
            source_component="TaskCoordinator",
            incoming_intent=intent_to_dict(intent),
            task_state_before=task_to_dict(active_task) if active_task else None,
        )

        trace(
            "task_coordinator.run.input",
            source_component="TaskCoordinator",
            incoming_intent=intent_to_dict(intent),
            active_task=task_to_dict(active_task) if active_task else None,
        )

        current_task_context = ""

        if active_task is not None:
            current_task_context = (
                json.dumps(
                    task_to_dict(active_task),
                    ensure_ascii=False,
                )
            )

        plan = self.planner.create_plan(
            intent,
            current_task_context=current_task_context,
        )

        trace(
            "task_coordinator.run.plan",
            plan=trace_plan_to_dict(plan),
        )

        if plan.status.value != "ready":
            trace(
                "task_coordinator.decision",
                decision="ABORT",
                reason="plan_not_ready",
                plan_status=plan.status.value,
            )
            return TaskExecution(plan=plan, results=[])

                # --- Email recipient normalisation ---
        if (
            plan.steps
            and plan.steps[0].action
            == "email_draft_create"
        ):
            step = plan.steps[0]

            recipient_raw = (
                step.parameters
                .get("recipient", "")
                .strip()
            )

            if recipient_raw:
                plain_email = (
                    self._normalize_email_recipient(
                        recipient_raw
                    )
                )

                if (
                    "@" not in plain_email
                    or "." not in plain_email.split("@")[-1]
                ):
                    plain_email = (
                        self.resolve_email_recipient(
                            plain_email
                        )
                        or ""
                    )

                if plain_email:
                    updated_parameters = dict(
                        step.parameters
                    )

                    updated_parameters[
                        "recipient"
                    ] = plain_email

                    plan = Plan(
                        goal=plan.goal,
                        confidence=plan.confidence,
                        steps=[
                            PlanStep(
                                action=step.action,
                                parameters=updated_parameters,
                                reason=step.reason,
                                original_input=(
                                    step.original_input
                                ),
                            )
                        ],
                        status=plan.status,
                    )

                    step = plan.steps[0]

                else:
                    trace(
                        "task_coordinator.decision",
                        decision="AWAIT_EMAIL_RECIPIENT",
                        recipient_name=recipient_raw,
                        plan_step_parameters=(
                            step.parameters
                        ),
                    )

                    task = self.task_manager.create(
                        [
                            step.action
                            for step in plan.steps
                        ]
                    )

                    self.task_manager.update_context(
                        task.task_id,
                        {
                            "recipient_name": (
                                recipient_raw
                            ),
                            "email_subject": (
                                step.parameters.get(
                                    "subject",
                                    "",
                                )
                            ),
                            "email_body": (
                                step.parameters.get(
                                    "body",
                                    "",
                                )
                            ),
                            "waiting_for": (
                                "email_recipient"
                            ),
                        },
                    )

                    self.task_manager.await_input(
                        task.task_id
                    )

                    return TaskExecution(
                        plan=plan,
                        results=[],
                        task=task,
                    )

                # ---------------------------------------------------------
        # Dynamic execution loop
        #
        # Execute one step.
        # Feed the authoritative result back to Gemini.
        # Gemini decides whether another step is needed.
        # ---------------------------------------------------------
        if not plan.steps:
            return TaskExecution(
                plan=plan,
                results=[],
            )

        task = self.task_manager.create(
            [plan.steps[0].action]
        )

        set_task_id(task.task_id)

        self.task_manager.start(
            task.task_id
        )

        results: list[ExecutionResult] = []

        current_step = plan.steps[0]

        while True:
            index = task.current_step

            trace(
                "task_coordinator.execute_step",
                decision="EXECUTE_STEP",
                step_index=index,
                action=current_step.action,
                parameters=current_step.parameters,
                task_id=task.task_id,
            )

            self.task_manager.start_step(
                task.task_id,
                index,
            )

            result = self.executor.execute(
                current_step
            )

            results.append(result)

            trace(
                "task_coordinator.step_result",
                step_index=index,
                execution_result=(
                    execution_result_to_dict(
                        result
                    )
                ),
            )

            if not result.success:
                self.task_manager.fail_step(
                    task.task_id,
                    index,
                    result.error
                    or "Execution failed.",
                )
                break

            # -----------------------------------------------------
            # Email draft creation creates a confirmation boundary.
            # No planner continuation is allowed past this point.
            # -----------------------------------------------------
            if (
                current_step.action
                == "email_draft_create"
                and result.data is not None
            ):
                draft = result.data

                self.task_manager.update_context(
                    task.task_id,
                    {
                        "gmail_draft_id": draft.draft_id,
                        "email_recipient": draft.recipient,
                        "email_subject": draft.subject,
                        "email_body": draft.body,
                    },
                )

                self.task_manager.complete_step(
                    task.task_id,
                    index,
                    result.data,
                )

                self.task_manager.await_confirmation(
                    task.task_id,
                    action="email_send",
                    summary=(
                        f"Email to {draft.recipient}; "
                        f"subject: {draft.subject}"
                    ),
                )

                break

            self.task_manager.complete_step(
                task.task_id,
                index,
                result.data,
            )

            # -----------------------------------------------------
            # Ask Gemini what happens next.
            # -----------------------------------------------------
            task_context = json.dumps(
                task_to_dict(task),
                ensure_ascii=False,
                default=str,
            )

            decision = self.planner.decide_next_step(
                intent=intent,
                task_context=task_context,
                executed_step=current_step,
                execution_result=(
                    execution_result_to_dict(
                        result
                    )
                ),
            )

            trace(
                "task_coordinator.next_step_decision",
                task_id=task.task_id,
                decision=decision,
            )

            if decision["decision"] == "done":
                break

            if decision["decision"] == "await_user":
                break

            next_step = decision.get(
                "step"
            )

            if next_step is None:
                break

            self.task_manager.append_step(
                task.task_id,
                next_step.action,
            )

            current_step = next_step

            trace(
                "task_coordinator.next_step",
                task_id=task.task_id,
                action=next_step.action,
                parameters=next_step.parameters,
                reason=next_step.reason,
            )

        trace(
            "task_coordinator.run.complete",
            task=task_to_dict(task),
            results=[
                execution_result_to_dict(r)
                for r in results
            ],
        )

        return TaskExecution(
            plan=plan,
            results=results,
            task=task,
        )

        trace(
            "TaskCoordinator.run.EXIT",
            source_component="TaskCoordinator",
            task_state_after=task_to_dict(task),
            results=[execution_result_to_dict(r) for r in results],
        )