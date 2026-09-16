# from advi.core import intent_detector
from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging

from ..io.output import AdviResponse
from .task import TaskStatus
from .executor import ExecutionResult
from ..memory.retriever import MemoryRetriever
from ..memory.session import SessionBuffer
from ..memory.short_term import ShortTermMemory
from ..providers import LLMProvider
from .capabilities import capability_for_prompt
from .intent import Intent, IntentType
from .intent_detector import IntentDetector
from .intent_handler import IntentHandler
from .intent_bridge import intent_from_reasoning
from advi.brain.reasoning import ReasoningEngine
from .personality import build_advi_system_prompt
from .pipeline_trace import (
    begin_turn,
    execution_result_to_dict,
    emit_turn_summary,
    intent_to_dict,
    next_llm_call_id,
    record_summary,
    set_task_id,
    task_to_dict,
    trace,
    trace_exception,
)
from .response_policy import build_response_policy
from .task_coordinator import TaskCoordinator
from .llm_telemetry import LLMTelemetry
from ..io.dev_display import (
    show_intent,
    show_plan,
    show_task,
    show_llm_summary,
)


logger = logging.getLogger(__name__)


@dataclass
class ConversationEngine:
    provider: LLMProvider
    memory: ShortTermMemory = field(
        default_factory=ShortTermMemory
    )
    session_buffer: SessionBuffer = field(
        default_factory=SessionBuffer
    )
    retriever: MemoryRetriever | None = None
    previous_session_context: str | None = None
    intent_detector: IntentDetector | None = None
    intent_handler: IntentHandler | None = None
    task_coordinator: TaskCoordinator | None = None
    telemetry: LLMTelemetry | None = None
    gmail_available: bool = False
    reasoning_engine: ReasoningEngine | None = None
    

    # def modify_current_task(
    #     self,
    #     updates: dict[str, str],
    # ):
    #     task = self.current_task

    #     if task is None:
    #         return None

    #     return self.task_manager.update_context(
    #         task.task_id,
    #         updates,
    #     )

    # def get_current_task_context(
    #     self,
    # ) -> dict[str, str]:
    #         task = self.current_task

    #         if task is None:
    #             return {}

    #         return dict(task.context)    

    def respond(
        self,
        user_input: str,
    ) -> AdviResponse:
        turn_id = begin_turn(user_input)
        text = user_input.strip()

        trace(
            "ConversationEngine.ENTER",
            source_component="ConversationEngine",
            turn_id=turn_id,
            input_text=text,
        )

        current_task = (
            self.task_coordinator.current_task
            if self.task_coordinator is not None
            else None
        )

        if current_task is not None:
            set_task_id(current_task.task_id)

        trace(
            "user.input",
            turn_id=turn_id,
            text=text,
            active_task_id=(
                current_task.task_id
                if current_task is not None
                else None
            ),
            active_task_status=(
                current_task.status.value
                if current_task is not None
                else None
            ),
        )

        record_summary(
            task_status_before=(
                current_task.status.value
                if current_task is not None
                else None
            ),
        )


        memory = None

        if self.task_coordinator is not None:
            memory = getattr(
                self.task_coordinator.executor,
                "memory",
                None,
            )

        if (
            current_task is not None
            and current_task.status
            == TaskStatus.AWAITING_INPUT
            and current_task.context.get(
                "waiting_for"
            )
            == "email_recipient"
        ):
            email_address = (
                memory.extract_email(text)
                if memory is not None
                and hasattr(
                    memory,
                    "extract_email",
                )
                else None
            )

            if email_address is None:
                logger.warning(
                    "Invalid or ambiguous email address supplied "
                    "for recipient %r: %r",
                    current_task.context.get(
                        "recipient_name",
                        "",
                    ),
                    text,
                )

                return AdviResponse(
                    "I couldn't identify a valid email address "
                    "from that. Please provide the email address "
                    "by itself."
                )

            self.task_coordinator.task_manager.update_context(
                current_task.task_id,
                {
                    "email_recipient": email_address,
                    "waiting_for": "",
                },
            )

            recipient_name = (
                current_task.context.get(
                    "recipient_name",
                    "",
                ).strip()
            )

            if (
                memory is not None
                and recipient_name
                and hasattr(
                    memory,
                    "save_contact",
                )
            ):
                memory.save_contact(
                    recipient_name,
                    email_address,
                )

                trace(
                    "email.contact_saved",
                    source_component="ConversationEngine",
                    name=recipient_name,
                    email=email_address,
                )

            return self._resume_email_task(
                current_task,
                email_address,
            )

        telemetry_start = (
            len(self.telemetry.calls)
            if self.telemetry is not None
            else 0
        )

        print()
        print("─" * 48)
        print(" USER")
        print("─" * 48)
        print(text)

        if not text:
            return AdviResponse("")


        detected_intent: Intent | None = None
        task_execution = None
        confirmed_execution_result = None

        if (
            detected_intent is None
            and self.intent_detector is not None
        ):
            if hasattr(
                self.intent_detector,
                "set_current_task",
            ):
                current_task = None

                if self.task_coordinator is not None:
                    current_task = (
                        self.task_coordinator.current_task
                    )

                self.intent_detector.set_current_task(
                    current_task
                )

            trace(
                "ConversationEngine.before_intent_detection",
                source_component="ConversationEngine",
            )
            if self.reasoning_engine is not None:
                reasoning_context = {
                    "active_task": (
                        {
                            "task_id": current_task.task_id,
                            "status": current_task.status.value,
                        }
                        if current_task is not None
                        else None
                    ),
                    "recent_history": self.session_buffer.get_messages()[-4:],
                    "available_capabilities": "legacy-conversation-engine",
                }
                decision = self.reasoning_engine.decide(text, reasoning_context)
                detected_intent = intent_from_reasoning(decision, text)
                trace(
                    "ConversationEngine.reasoning_decision",
                    source_component="ConversationEngine",
                    mode=decision.mode,
                    action=decision.action,
                    confidence=decision.confidence,
                )
            else:
                detected_intent = self.intent_detector.detect(text)
            trace(
                "ConversationEngine.after_intent_detection",
                source_component="ConversationEngine",
                intent=intent_to_dict(detected_intent),
            )
            record_summary(intent=detected_intent.type.value)

            trace(
                "conversation.intent_received",
                source_component="ConversationEngine",
                intent=intent_to_dict(detected_intent),
            )


        current_task = None

        if self.task_coordinator is not None:
            current_task = (
                self.task_coordinator.current_task
            )

        if (
            current_task is not None
            and detected_intent is not None
            and detected_intent.confidence >= 0.90
            and detected_intent.type
            not in {
                IntentType.TASK_CONFIRMATION,
                IntentType.TASK_REJECTION,
                IntentType.TASK_MODIFICATION,
                IntentType.TASK_PAUSE,
                IntentType.TASK_RESUME,
                IntentType.TASK_CANCEL,
                IntentType.TASK_READBACK,
            }
            and detected_intent.type
            not in {
                IntentType.CONVERSATION,
            }
        ):
            self.task_coordinator.pause_current_task()   



          


        task_control_result = None    

        if (
            detected_intent is not None
            and self.task_coordinator is not None
            and detected_intent.confidence >= 0.90
            and detected_intent.type in {
                IntentType.TASK_CONFIRMATION,
                IntentType.TASK_REJECTION,
                IntentType.TASK_PAUSE,
                IntentType.TASK_RESUME,
                IntentType.TASK_CANCEL,
            }
        ):
            task_control_result = (
                self.task_coordinator.handle_task_intent(
                    detected_intent
                )
            )

            if isinstance(
                task_control_result,
                ExecutionResult,
            ):
                confirmed_execution_result = (
                    task_control_result
                )

        operation_context: list[str] = []


        if (
            current_task is not None
            and self.task_coordinator.current_task is None
            and detected_intent is not None
            and detected_intent.type
            not in {
                IntentType.TASK_CONFIRMATION,
                IntentType.TASK_REJECTION,
                IntentType.TASK_MODIFICATION,
                IntentType.TASK_PAUSE,
                IntentType.TASK_RESUME,
                IntentType.TASK_CANCEL,
                IntentType.TASK_READBACK,
                IntentType.CONVERSATION,
            }
        ):
            operation_context.append(
                "Previous task was paused because "
                "the user started a different request."
            )  

        if (
            self.task_coordinator is not None
            and detected_intent is not None
            and detected_intent.type
            == IntentType.TASK_READBACK
        ):
            readback = (
                self.task_coordinator
                .handle_task_intent(
                    detected_intent
                )
            )

            if readback is not None:
                operation_context.append(
                    "Current email draft:\n"
                    f"- recipient: "
                    f"{readback.recipient}\n"
                    f"- subject: "
                    f"{readback.subject}\n"
                    f"- body: "
                    f"{readback.body}"
                )
            else:
                task_context = (
                    self.task_coordinator
                    .get_current_task_context()
                )

                if task_context:
                    context_lines = "\n".join(
                        f"- {key}: {value}"
                        for key, value
                        in task_context.items()
                    )

                    operation_context.append(
                        "Current task content for readback:\n"
                        + context_lines
                    )

        # ---------------------------------------------------------
        # Email composition
        #
        # Gemini determines what the user wants.
        # Groq completes missing email wording.
        # Gmail execution remains deterministic and happens later.
        # ---------------------------------------------------------
        if (
            detected_intent is not None
            and detected_intent.type
            == IntentType.EMAIL_DRAFT_CREATE
        ):
            trace(
                "ConversationEngine.before_email_composition",
                source_component="ConversationEngine",
                intent=intent_to_dict(detected_intent),
            )
            detected_intent = (
                self._compose_email_draft(
                    detected_intent
                )
            )
            trace(
                "ConversationEngine.after_email_composition",
                source_component="ConversationEngine",
                intent=intent_to_dict(detected_intent),
            )

            trace(
                "conversation.email_intent_completed",
                source_component="ConversationEngine",
                intent=intent_to_dict(
                    detected_intent
                ),
            )            

        if detected_intent is not None:
            intent_preview = {
                "intent": detected_intent.type.value,
                "confidence": round(
                    detected_intent.confidence,
                    2,
                ),
            }

            if detected_intent.target is not None:
                intent_preview["target"] = (
                    detected_intent.target
                )

            if detected_intent.entities:
                intent_preview["entities"] = (
                    detected_intent.entities
                )

            logger.info(
                "Intent: %s",
                json.dumps(
                    intent_preview,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )

            task_execution = None

            if (
                detected_intent is not None
                and self.task_coordinator is not None
                and detected_intent.type
                not in {
                    IntentType.TASK_CONFIRMATION,
                    IntentType.TASK_REJECTION,
                    IntentType.TASK_MODIFICATION,
                    IntentType.TASK_PAUSE,
                    IntentType.TASK_RESUME,
                    IntentType.TASK_CANCEL,
                    IntentType.TASK_READBACK,
                }
            ):
                trace(
                    "ConversationEngine.before_task_coordinator",
                    source_component="ConversationEngine",
                    intent=intent_to_dict(detected_intent),
                )
                task_execution = (
                    self.task_coordinator.run(
                        detected_intent
                    )
                )
                trace(
                    "ConversationEngine.after_task_coordinator",
                    source_component="ConversationEngine",
                    task_execution=task_execution,
                )
                record_summary(
                    plan=task_execution.plan.goal,
                    task_status_after=(
                        task_execution.task.status.value
                        if task_execution.task is not None
                        else None
                    ),
                )

            if task_execution is not None:
                show_plan(
                    task_execution.plan
                )

                if task_execution.task is not None:
                    show_task(
                        task_execution.task
                    )
                    # ---- Display the full email draft from authoritative context ----
                    task = task_execution.task
                    if task.context.get("email_recipient") and task.context.get("email_body"):
                        print("\n" + "─" * 48)
                        print(" EMAIL DRAFT (stored)")
                        print("─" * 48)
                        print(f"To      : {task.context.get('email_recipient', '')}")
                        print(f"Subject : {task.context.get('email_subject', '')}")
                        print("\n" + task.context.get('email_body', ''))
                        print("─" * 48)
                        print("Would you like me to send this email?")

        # operation_context: list[str] = []


        if task_control_result is not None:
            if isinstance(
                task_control_result,
                ExecutionResult,
            ):
                operation_context.append(
                    "Confirmed action execution result:\n"
                    + json.dumps(
                        execution_result_to_dict(
                            task_control_result
                        ),
                        ensure_ascii=False,
                    )
                )
            else:
                status = getattr(
                    task_control_result,
                    "status",
                    None,
                )

                if status is not None:
                    operation_context.append(
                        "Task state update:\n"
                        f"- status: {status.value}"
                    )

        if (
            self.task_coordinator is not None
            and detected_intent is not None
            and detected_intent.type
            == IntentType.TASK_MODIFICATION
        ):
            task_context = (
                self.task_coordinator
                .get_current_task_context()
            )

            if task_context:
                context_lines = "\n".join(
                    f"- {key}: {value}"
                    for key, value
                    in task_context.items()
                )

                operation_context.append(
                    "Updated task context:\n"
                    + context_lines
                )

        if (
            self.task_coordinator is not None
            and detected_intent is not None
            and detected_intent.type
            == IntentType.TASK_READBACK
        ):
            task_context = (
                self.task_coordinator
                .get_current_task_context()
            )

            if task_context:
                context_lines = "\n".join(
                    f"- {key}: {value}"
                    for key, value
                    in task_context.items()
                )

                operation_context.append(
                    "Current task content for readback:\n"
                    + context_lines
                )

                

        # ---------------------------------------------------------
        # 1. Perform persistent-memory operations when intent
        #    confidence is high enough.
        #
        #    IMPORTANT:
        #    These operations do not generate the user-facing answer.
        #    The final conversational LLM always does that.
        # ---------------------------------------------------------
        if (
            detected_intent is not None
            and detected_intent.confidence >= 0.90
            and self.intent_handler is not None
        ):
            if detected_intent.type in {
                IntentType.MEMORY_UPDATE,
                IntentType.MEMORY_FORGET,
            }:
                _, operation_result = (
                    self.intent_handler.handle(
                        text,
                        detected_intent,
                    )
                )

                operation_context.append(
                    self._format_memory_operation_context(
                        detected_intent,
                        operation_result,
                    )
                )

        # ---------------------------------------------------------
        # 2. Store user message in short-term memory
        # ---------------------------------------------------------
        evicted = self.memory.add(
            "user",
            text,
        )

        self.session_buffer.add(evicted)

        messages = self.memory.get_messages()
        request_messages = list(messages)

        system_parts: list[str] = []
        context_sources: dict[str, str | list[str]] = {}

        # ---------------------------------------------------------
        # 3. Capability state
        # ---------------------------------------------------------
        capability_text = capability_for_prompt(
            email_available=self.gmail_available
        )
        system_parts.append(capability_text)
        context_sources["capabilities"] = capability_text

        # ---------------------------------------------------------
        # 4. Memory retrieval
        # ---------------------------------------------------------
        if (
            self.retriever is not None
            and detected_intent is not None
            and detected_intent.type
            in {
                IntentType.MEMORY_RETRIEVAL,
                IntentType.MEMORY_UPDATE,
                IntentType.MEMORY_FORGET,
            }
        ):
            # If the intent identifies a specific memory key,
            # retrieve that exact fact first.
            if (
                detected_intent is not None
                and detected_intent.type
                == IntentType.MEMORY_RETRIEVAL
                and detected_intent.target
            ):
                exact_memory = (
                    self.retriever.memory.recall(
                        "user",
                        detected_intent.target,
                    )
                )

                if exact_memory is not None:
                    system_parts.append(
                        "Exact requested memory:\n"
                        f"- {exact_memory.statement}"
                    )

            # Semantic retrieval remains useful as additional context,
            # especially for broad or paraphrased questions.
            retrieved = self.retriever.search(
                text,
                limit=12,
            )

            if retrieved:
                memory_context = "\n".join(
                    f"- {item.memory.statement}"
                    for item in retrieved
                )

                memory_block = (
                    "Relevant long-term memories:\n"
                    + memory_context
                )
                system_parts.append(memory_block)
                context_sources["memory_retrieval"] = memory_block

            # -----------------------------------------------------
            # 5. Relationship retrieval
            # -----------------------------------------------------
            relationship_rows = (
                self.retriever.memory
                .search_relationships(
                    text,
                    limit=12,
                )
            )

            if relationship_rows:
                relationship_context = "\n".join(
                    (
                        f"- {item.subject} "
                        f"{item.relation} "
                        f"{item.object}"
                    )
                    for item in relationship_rows
                )

                relationship_block = (
                    "Relevant relationship facts:\n"
                    + relationship_context
                )
                system_parts.append(relationship_block)
                context_sources["relationships"] = relationship_block

        # ---------------------------------------------------------
        # 6. Memory operation result
        # ---------------------------------------------------------
        system_parts.extend(
            operation_context
        )

        # ---------------------------------------------------------
        # 7. Previous session summaries
        # ---------------------------------------------------------
        if self.previous_session_context:
            session_block = (
                "Recent session context:\n"
                + self.previous_session_context
            )
            system_parts.append(session_block)
            context_sources["session"] = session_block

                # ---------------------------------------------------------
        # 7.1. Task execution results
        # ---------------------------------------------------------
        # Email drafts are authoritative structured objects.
        # Never ask the conversational LLM to reconstruct their
        # contents from a generic repr() or from conversation history.
        if task_execution is not None:
            execution_context = []

            for result in task_execution.results:
                if result.success:
                    data_recipient = getattr(
                        result.data,
                        "recipient",
                        None,
                    )
                    data_subject = getattr(
                        result.data,
                        "subject",
                        None,
                    )
                    data_body = getattr(
                        result.data,
                        "body",
                        None,
                    )

                    is_draft_like = (
                        data_recipient is not None
                    )

                    if is_draft_like:
                        execution_context.append(
                            f"- Action: {result.action}\n"
                            f"Recipient: {data_recipient}\n"
                            f"Subject: {data_subject}\n"
                            f"Body:\n{data_body}\n"
                            "(This is the EXACT "
                            "recipient/subject/body. "
                            "Quote these fields verbatim when "
                            "telling the user what the email "
                            "says. Do not paraphrase, reword, "
                            "or invent different wording.)"
                        )
                    else:
                        execution_context.append(
                            f"- Action: {result.action}\n"
                            f"Result: {result.data}"
                        )
                else:
                    execution_context.append(
                        f"- Action: {result.action}\n"
                        f"Failed: {result.error}"
                    )

            if execution_context:
                execution_block = (
                    "Task execution results:\n"
                    + "\n".join(execution_context)
                )

                system_parts.append(
                    execution_block
                )

                context_sources[
                    "task_execution"
                ] = execution_block

        # ---------------------------------------------------------
        # 7.2. VERIFIED ACTION RESULT
        # ---------------------------------------------------------
        # Combine execution results from normal task execution and
        # confirmation-controlled execution so the final LLM sees
        # one authoritative execution stream.
        authoritative_execution_results: list[ExecutionResult] = []

        if task_execution is not None:
            authoritative_execution_results.extend(
                task_execution.results
            )

        if confirmed_execution_result is not None:
            authoritative_execution_results.append(
                confirmed_execution_result
            )

        if authoritative_execution_results:
            # Make confirmation execution visible in the same
            # authoritative context as normal execution.
            if confirmed_execution_result is not None:
                confirmation_execution_block = (
                    "Task confirmation execution result:\n"
                    + json.dumps(
                        execution_result_to_dict(
                            confirmed_execution_result
                        ),
                        ensure_ascii=False,
                    )
                )

                system_parts.append(
                    confirmation_execution_block
                )

                context_sources[
                    "confirmation_execution"
                ] = confirmation_execution_block

            execution_context = []

            for result in authoritative_execution_results:
                if result.success:
                    data_recipient = getattr(
                        result.data,
                        "recipient",
                        None,
                    )
                    data_subject = getattr(
                        result.data,
                        "subject",
                        None,
                    )
                    data_body = getattr(
                        result.data,
                        "body",
                        None,
                    )

                    is_draft_like = (
                        data_recipient is not None
                    )

                    if is_draft_like:
                        execution_context.append(
                            f"- Action: {result.action}\n"
                            f"Recipient: {data_recipient}\n"
                            f"Subject: {data_subject}\n"
                            f"Body:\n{data_body}\n"
                            "(This is the EXACT "
                            "recipient/subject/body. "
                            "Quote these fields verbatim when "
                            "telling the user what the email "
                            "says. Do not paraphrase, reword, "
                            "or invent different wording.)"
                        )
                    else:
                        execution_context.append(
                            f"- Action: {result.action}\n"
                            f"Result: {result.data}"
                        )
                else:
                    execution_context.append(
                        f"- Action: {result.action}\n"
                        f"Failed: {result.error}"
                    )

            if execution_context:
                execution_block = (
                    "Task execution results:\n"
                    + "\n".join(execution_context)
                )

                system_parts.append(
                    execution_block
                )

                context_sources[
                    "task_execution"
                ] = execution_block

            failed_actions = [
                result
                for result in authoritative_execution_results
                if not result.success
            ]

            successful_email_send = any(
                result.success
                and result.action == "email_send"
                for result in authoritative_execution_results
            )

            failed_email_send = any(
                not result.success
                and result.action == "email_send"
                for result in authoritative_execution_results
            )

            draft_created_only = (
                not successful_email_send
                and not failed_email_send
                and any(
                    result.success
                    and result.action
                    == "email_draft_create"
                    for result in authoritative_execution_results
                )
            )

            if failed_actions:
                failure_lines = [
                    "VERIFIED ACTION RESULT:",
                    "- One or more requested actions failed.",
                    "- The requested action was NOT completed.",
                    "- Python execution is authoritative.",
                    "- Do not claim that the failed action succeeded.",
                    "- Do not pretend that the requested result was created, sent, saved, or completed.",
                    "- Do not silently retry or recreate the failed action in the final response.",
                ]

                for failed_result in failed_actions:
                    failure_lines.extend(
                        [
                            (
                                f"- Failed action: "
                                f"{failed_result.action}"
                            ),
                            (
                                f"- Error: "
                                f"{failed_result.error}"
                            ),
                        ]
                    )

                failure_lines.append(
                    "- Explain the failure honestly and briefly."
                )

                system_parts.append(
                    "\n".join(failure_lines)
                )

            elif successful_email_send:
                system_parts.append(
                    "VERIFIED ACTION RESULT:\n"
                    "- The email_send action succeeded.\n"
                    "- Gmail confirmed the email was sent.\n"
                    "- You may tell the user the email was sent."
                )

            elif draft_created_only:
                system_parts.append(
                    "VERIFIED ACTION RESULT:\n"
                    "- A draft was created.\n"
                    "- NO email_send action has run yet.\n"
                    "- The email has NOT been sent.\n"
                    "- Do not say or imply the email was sent, "
                    "delivered, or completed.\n"
                    "- Read the draft back using the exact "
                    "recipient, subject, and body above.\n"
                    "- Ask the user to confirm before sending."
                )

        elif (
            detected_intent is not None
            and detected_intent.type
            == IntentType.TASK_CONFIRMATION
        ):
            system_parts.append(
                "VERIFIED ACTION RESULT:\n"
                "- No email_send action was executed.\n"
                "- Do not claim that an email was sent."
            )

        # ---------------------------------------------------------
        # 8. Build system context
        # ---------------------------------------------------------
        system_content = build_advi_system_prompt()

        system_content += (
            "\n\nEXECUTION TRUTH RULE:\n"
            "Python tool execution results are authoritative.\n"
            "If an action failed, the action did not happen.\n"
            "Never convert a failed tool execution into a successful-looking response.\n"
            "Never fulfill the same failed action again merely because "
            "the user's original request asked for it.\n"
            "Explain the failure and state what is needed to proceed."
        )

        system_content += (
            "\n\n"
            + build_response_policy(text)
        )

        if detected_intent is not None:
            system_content += (
                "\n\n"
                "Internal intent classification:\n"
                f"- intent: {detected_intent.type.value}\n"
                f"- confidence: "
                f"{detected_intent.confidence:.2f}\n"
            )

            if detected_intent.target:
                system_content += (
                    f"- target: "
                    f"{detected_intent.target}\n"
                )

            system_content += (
                "Use this classification as routing context; "
                "do not mention internal classification to the user."
            )

        if system_parts:
            system_content += (
                "\n\nContext available for this request:\n"
                + "\n\n".join(system_parts)
                + "\n\n"
                "Use this context only when relevant. "
                "Answer the user's actual question."
            )

        request_messages.insert(
            0,
            {
                "role": "system",
                "content": system_content,
            },
        )

        verified_action_present = any(
            "VERIFIED ACTION RESULT" in part
            for part in system_parts
        )

        trace(
            "conversation.final_llm_context",
            source_component="ConversationEngine",
            user_input=text,
            active_task=(
                task_to_dict(current_task)
                if current_task is not None
                else None
            ),
            detected_intent=(
                intent_to_dict(detected_intent)
                if detected_intent is not None
                else None
            ),
            task_execution_results=(
                [
                    execution_result_to_dict(r)
                    for r in task_execution.results
                ]
                if task_execution is not None
                else None
            ),
            context_sources=context_sources,
            operation_context=operation_context,
            system_prompt=system_content,
            request_messages=request_messages,
            verified_action_result_in_prompt=verified_action_present,
            note=(
                "VERIFIED ACTION RESULT blocks are now included "
                "BEFORE the Groq call (see system_parts)."
            ),
        )

        # ---------------------------------------------------------
        # 9. FINAL conversational LLM call
        # ---------------------------------------------------------
        final_llm_call_id = next_llm_call_id()
        trace(
            "ConversationEngine.before_final_groq_call",
            source_component="ConversationEngine",
            llm_call_id=final_llm_call_id,
            provider=getattr(self.provider, "name", type(self.provider).__name__),
            model=getattr(self.provider, "model", None),
            purpose="final_response",
            request_messages=request_messages,
        )
        try:
            result = self.provider.chat(
                request_messages
            )
        except Exception as exc:
            trace_exception(
                "ConversationEngine.final_groq_error",
                exc,
                llm_call_id=final_llm_call_id,
                provider=getattr(self.provider, "name", type(self.provider).__name__),
                model=getattr(self.provider, "model", None),
                purpose="final_response",
            )
            raise

        trace(
            "ConversationEngine.after_final_groq_call",
            source_component="ConversationEngine",
            llm_call_id=final_llm_call_id,
            provider=getattr(result, "provider", None),
            model=getattr(result, "model", None),
            purpose="final_response",
            response=result,
        )

        authoritative_results = [
            execution_result_to_dict(result)
            for result in authoritative_execution_results
        ]

        final_task = (
            self.task_coordinator.current_task
            if self.task_coordinator is not None
            else None
        )

        trace(
            "conversation.final_response",
            source_component="ConversationEngine",
            final_response_text=result.text,
            response_source=getattr(result, "provider", None),
            action_executed=bool(authoritative_results),
            authoritative_execution_results=authoritative_results,
            task_status=(
                final_task.status.value
                if final_task is not None
                else None
            ),
            verified_action_appended_after_groq=False,  # now included before
            verified_action_blocks_now_in_system_parts=[
                part for part in system_parts
                if "VERIFIED ACTION RESULT" in part
            ],
        )

        if self.telemetry is not None:
            self.telemetry.record(
                result,
                "final_response",
            )

        if self.telemetry is not None:
            show_llm_summary(
                self.telemetry.records_since(
                    telemetry_start
                )
            )    

        # ---------------------------------------------------------
        # 10. Store assistant response
        # ---------------------------------------------------------
        evicted = self.memory.add(
            "assistant",
            result.text,
        )

        self.session_buffer.add(evicted)

        record_summary(
            executed_action=(
                authoritative_execution_results[-1].action
                if authoritative_execution_results
                else None
            ),
            execution_success=(
                authoritative_execution_results[-1].success
                if authoritative_execution_results
                else None
            ),
            task_status_after=(
                final_task.status.value
                if final_task is not None
                else None
            ),
            final_response_generated=True,
        )
        trace(
            "ConversationEngine.EXIT",
            source_component="ConversationEngine",
            final_response=result.text,
            task_status=(
                final_task.status.value
                if final_task is not None
                else None
            ),
        )
        emit_turn_summary()

        return AdviResponse(
            result.text
        )



    def _compose_email_draft(
        self,
        intent: Intent,
    ) -> Intent:
        """
        Let Groq compose the complete email.

        Gemini decides what the user wants.
        Groq decides how the email should be written.
        Python/Gmail remains authoritative for execution.

        Explicit recipient identity is never invented.
        The email body/subject may be rewritten for quality.
        """
        if intent.type != IntentType.EMAIL_DRAFT_CREATE:
            return intent

        entities = dict(intent.entities)
        parameters = dict(intent.parameters)

        recipient = (
            entities.get("recipient")
            or parameters.get("recipient")
            or ""
        ).strip()

        requested_body = (
            entities.get("body")
            or parameters.get("body")
            or ""
        ).strip()

        requested_subject = (
            entities.get("subject")
            or parameters.get("subject")
            or ""
        ).strip()

        style = (
            entities.get("style")
            or parameters.get("style")
            or ""
        ).strip()

        if not recipient:
            return intent

        system_prompt = (
            "You are ADVI's email writing component.\n\n"
            "Write the COMPLETE email requested by the user.\n"
            "You have freedom to improve wording, grammar, structure, "
            "politeness, warmth, professionalism, and clarity.\n\n"
            "Rules:\n"
            "1. Never invent or change the recipient.\n"
            "2. Preserve the user's intended meaning.\n"
            "3. Turn rough instructions into a natural, polished email.\n"
            "4. Follow the requested tone or style.\n"
            "5. Create a sensible subject if one was not provided.\n"
            "6. Create the complete body, even when the user's input is "
            "only a short instruction.\n"
            "7. Do not send the email.\n"
            "8. Return ONLY the following format.\n\n"
            "SUBJECT: <subject>\n"
            "BODY:\n"
            "<complete email body>\n"
            "END_BODY"
        )

        user_prompt = (
            f"Original user request:\n"
            f"{intent.original_input}\n\n"
            f"Recipient:\n"
            f"{recipient}\n\n"
            f"User-provided subject:\n"
            f"{requested_subject or '<none>'}\n\n"
            f"User-provided message/instructions:\n"
            f"{requested_body or '<none>'}\n\n"
            f"Requested style:\n"
            f"{style or '<none>'}\n\n"
            "Compose the final email now."
        )

        try:
            llm_call_id = next_llm_call_id()
            trace(
                "ConversationEngine.email_composition_provider_request",
                provider=getattr(self.provider, "name", type(self.provider).__name__),
                model=getattr(self.provider, "model", None),
                purpose="email_composition",
                llm_call_id=llm_call_id,
                recipient=recipient,
                subject=requested_subject,
                body=requested_body,
            )
            result = self.provider.chat(
                [
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {
                        "role": "user",
                        "content": user_prompt,
                    },
                ]
            )

            raw = result.text.strip()

            if "SUBJECT:" not in raw:
                logger.warning(
                    "Groq email composition returned no SUBJECT."
                )
                return intent

            if "BODY:" not in raw:
                logger.warning(
                    "Groq email composition returned no BODY."
                )
                return intent

            subject = raw.split(
                "SUBJECT:",
                1,
            )[1].split(
                "BODY:",
                1,
            )[0].strip()

            body = raw.split(
                "BODY:",
                1,
            )[1]

            if "END_BODY" in body:
                body = body.split(
                    "END_BODY",
                    1,
                )[0]

            body = body.strip()

            if not subject or not body:
                logger.warning(
                    "Groq email composition returned an incomplete email."
                )
                return intent

            entities["recipient"] = recipient
            entities["subject"] = subject
            entities["body"] = body

            parameters["recipient"] = recipient
            parameters["subject"] = subject
            parameters["body"] = body

            trace(
                "email.composition.complete",
                source_component="ConversationEngine",
                original_input=intent.original_input,
                composed_subject=subject,
                composed_body=body,
                final_entities=entities,
                final_parameters=parameters,
            )

            return Intent(
                type=intent.type,
                confidence=intent.confidence,
                original_input=intent.original_input,
                target=intent.target,
                entities=entities,
                parameters=parameters,
            )

        except Exception:
            logger.exception(
                "Email composition with Groq failed."
            )
            return intent   


    def _resume_email_task(
        self,
        task,
        email_address: str,
    ) -> AdviResponse:
        """Resume an email task after the user supplies a recipient."""

        context = (
            self.task_coordinator
            .get_current_task_context()
        )

        recipient_name = context.get(
            "recipient_name",
            "the recipient",
        )

        subject = context.get(
            "email_subject",
            "",
        )

        body = context.get(
            "email_body",
            "",
        )

        if not subject:
            subject = "Email from ADVI"

        if not body:
            body = (
                "Please continue the email "
                "using the original request."
            )

        intent = Intent(
            type=IntentType.EMAIL_DRAFT_CREATE,
            confidence=1.0,
            original_input=(
                f"Continue the email task for "
                f"{recipient_name} using "
                f"{email_address}."
            ),
            entities={
                "recipient": email_address,
                "subject": subject,
                "body": body,
            },
        )

        execution = (
            self.task_coordinator.run(
                intent
            )
        )

        if execution.task is not None:
            show_plan(execution.plan)
            show_task(execution.task)

        operation_context = [
            (
                f"I found the email address for "
                f"{recipient_name}: {email_address}."
            )
        ]

        if execution.results:
            for result in execution.results:
                if result.success:
                    operation_context.append(
                        f"Email action completed: "
                        f"{result.action}."
                    )
                else:
                    operation_context.append(
                        f"Email action failed: "
                        f"{result.error}"
                    )

        system_content = (
            build_advi_system_prompt()
            + "\n\n"
            + build_response_policy(
                email_address
            )
            + "\n\n"
            "Task continuation:\n"
            + "\n".join(
                f"- {item}"
                for item in operation_context
            )
            + "\n\n"
            "Tell the user briefly what happened "
            "and, if the email draft is awaiting "
            "confirmation, offer to read it back "
            "or make changes before sending."
        )

        result = self.provider.chat(
            [
                {
                    "role": "system",
                    "content": system_content,
                },
                {
                    "role": "user",
                    "content": email_address,
                },
            ]
        )

        if self.telemetry is not None:
            self.telemetry.record(
                result,
                "email_task_resume",
            )

        evicted = self.memory.add(
            "assistant",
            result.text,
        )

        self.session_buffer.add(evicted)

        return AdviResponse(
            result.text
        )    

    @staticmethod
    def _format_memory_operation_context(
        intent: Intent,
        result,
    ) -> str:
        if intent.type == IntentType.MEMORY_UPDATE:
            if result is None:
                return (
                    "Memory operation: no memory decision was produced."
                )

            operation = result.operation.value

            if operation == "create":
                return (
                    "Memory operation: the requested information "
                    "was stored as a new durable memory."
                )

            if operation == "update":
                return (
                    "Memory operation: an existing durable memory "
                    "was updated according to the memory conflict rules."
                )

            if operation == "keep":
                return (
                    "Memory operation: the information was already "
                    "represented by an existing memory."
                )

            return (
                "Memory operation: the information was not stored."
            )

        if intent.type == IntentType.MEMORY_FORGET:
            if result is True:
                return (
                    "Memory operation: the requested memory "
                    "was successfully forgotten."
                )

            return (
                "Memory operation: no sufficiently reliable "
                "memory was identified for deletion."
            )

        return ""
        
    def get_session_buffer(
        self,
    ) -> list[dict[str, str]]:
        return [
            message.copy()
            for message in self.session_buffer.messages
        ] + self.memory.get_messages()