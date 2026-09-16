# rom cognee.infrastructure.databases.graph.postgres import PostgresGraphDatasetDatabaseHandler
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from .pipeline_trace import (
    execution_result_to_dict,
    trace,
    trace_exception,
)
from .planner import PlanStep

from ..integrations.gmail import GmailService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExecutionResult:
    action: str
    success: bool
    data: Any = None
    error: str | None = None


class Executor:
    """Execute approved planner actions."""

    ALLOWED_ACTIONS = {
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
        # Desktop
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
        # Browser
        "navigate",
        "search",
        "click_web_element",
        "read_web_page",
        # Files
        "save_file",
        "create_file",
        "read_file",
        "delete_file",
    }

    def __init__(
        self,
        *,
        memory=None,
        retriever=None,
        intent_handler=None,
        gmail_service: GmailService | None = None,
        engine=None,
    ) -> None:
        self.memory = memory
        self.retriever = retriever
        self.intent_handler = intent_handler
        self.gmail_service = gmail_service
        if engine is not None:
            self.engine = engine
        else:
            from advi.capabilities.registry import build_default_registry
            from advi.core.execution_engine import ExecutionEngine
            registry = build_default_registry(
                memory=memory,
                retriever=retriever,
                gmail_service=gmail_service,
            )
            self.engine = ExecutionEngine(registry=registry)

    def execute(
        self,
        step: PlanStep,
    ) -> ExecutionResult:
        trace(
            "Executor.ENTER",
            source_component="Executor",
            action=step.action,
            parameters=step.parameters,
        )
        trace(
            "executor.input",
            source_component="Executor",
            action=step.action,
            parameters=step.parameters,
            original_input=step.original_input,
            reason=step.reason,
            gmail_available=self.gmail_service is not None,
            memory_available=self.memory is not None,
            retriever_available=self.retriever is not None,
            intent_handler_available=self.intent_handler is not None,
        )

        if step.action not in self.ALLOWED_ACTIONS:
            result = ExecutionResult(
                action=step.action,
                success=False,
                error="Action is not allowed.",
            )
            trace(
                "executor.rejected",
                reason="action_not_allowed",
                allowed_actions=sorted(self.ALLOWED_ACTIONS),
                result=execution_result_to_dict(result),
            )
            return result

        handler = getattr(
            self,
            f"_execute_{step.action}",
            None,
        )

        handler_name = (
            f"_execute_{step.action}"
            if handler is not None
            else None
        )

        trace(
            "executor.dispatch",
            requested_action=step.action,
            allowed_actions=sorted(self.ALLOWED_ACTIONS),
            selected_handler=handler_name,
            handler_found=handler is not None,
        )

        if handler is None:
            # Delegate to unified ExecutionEngine
            from advi.core.action_plan import Action as EngineAction
            eng_action = EngineAction(
                action=step.action,
                parameters=step.parameters,
                reason=step.reason,
            )
            eng_res = self.engine.execute_action(eng_action)
            return ExecutionResult(
                action=eng_res.action,
                success=eng_res.success,
                data=eng_res.data,
                error=eng_res.error,
            )

        try:
            result = handler(step)
        except Exception as exc:
            trace_exception(
                "executor.error",
                exc,
                action=step.action,
                parameters=step.parameters,
            )
            result = ExecutionResult(
                action=step.action,
                success=False,
                error=str(exc),
            )

        trace(
            "executor.result",
            source_component="Executor",
            result=execution_result_to_dict(result),
            next="TaskCoordinator -> TaskManager.complete_step|fail_step",
        )

        trace(
            "Executor.EXIT",
            source_component="Executor",
            execution_result=execution_result_to_dict(result),
        )

        return result

    def _execute_memory_retrieval(
        self,
        step: PlanStep,
    ) -> ExecutionResult:
        if self.retriever is None:
            return ExecutionResult(
                action=step.action,
                success=False,
                error="Memory retriever is unavailable.",
            )

        query = step.original_input

        results = self.retriever.search(
            query,
            limit=8,
        )

        return ExecutionResult(
            action=step.action,
            success=True,
            data=results,
        )

    def _execute_memory_update(
        self,
        step: PlanStep,
    ) -> ExecutionResult:
        if self.intent_handler is None:
            return ExecutionResult(
                action=step.action,
                success=False,
                error="Intent handler is unavailable.",
            )

        try:
            intent, result = self.intent_handler.handle(
                step.original_input
            )

            return ExecutionResult(
                action=step.action,
                success=True,
                data=result,
            )

        except Exception as exc:
            trace_exception(
                "executor.memory_update_error",
                exc,
                action=step.action,
                parameters=step.parameters,
            )
            return ExecutionResult(
                action=step.action,
                success=False,
                error=str(exc),
            )

    def _execute_memory_forget(
        self,
        step: PlanStep,
    ) -> ExecutionResult:
        if self.intent_handler is None:
            return ExecutionResult(
                action=step.action,
                success=False,
                error="Intent handler is unavailable.",
            )

        try:
            intent, result = self.intent_handler.handle(
                step.original_input
            )

            return ExecutionResult(
                action=step.action,
                success=True,
                data=result,
            )

        except Exception as exc:
            trace_exception(
                "executor.memory_forget_error",
                exc,
                action=step.action,
                parameters=step.parameters,
            )
            return ExecutionResult(
                action=step.action,
                success=False,
                error=str(exc),
            )

    def _execute_capability_query(
        self,
        step: PlanStep,
    ) -> ExecutionResult:
        return ExecutionResult(
            action=step.action,
            success=True,
        )

    def _execute_identity_query(
        self,
        step: PlanStep,
    ) -> ExecutionResult:
        return ExecutionResult(
            action=step.action,
            success=True,
        )

    def _execute_conversation(
        self,
        step: PlanStep,
    ) -> ExecutionResult:
        return ExecutionResult(
            action=step.action,
            success=True,
        )

    def _execute_email_draft_create(
            self,
            step: PlanStep,
        ) -> ExecutionResult:
            if self.gmail_service is None:
                return ExecutionResult(
                    action=step.action,
                    success=False,
                    error="Gmail service is unavailable.",
                )

            recipient = step.parameters.get(
                "recipient"
            )
            subject = step.parameters.get(
                "subject"
            )
            body = step.parameters.get(
                "body"
            )

            if not (
                recipient
                and subject
                and body
            ):
                return ExecutionResult(
                    action=step.action,
                    success=False,
                    error=(
                        "Email draft requires "
                        "recipient, subject, and body."
                    ),
                )

            draft = self.gmail_service.create_draft(
                to=recipient,
                subject=subject,
                body=body,
            )

            return ExecutionResult(
                action=step.action,
                success=True,
                data=draft,
            )  

    def _execute_email_draft_read(
        self,
        step: PlanStep,
    ) -> ExecutionResult:
        if self.gmail_service is None:
            return ExecutionResult(
                action=step.action,
                success=False,
                error="Gmail service is unavailable.",
            )

        draft_id = step.parameters.get(
            "draft_id"
        )

        if not draft_id:
            return ExecutionResult(
                action=step.action,
                success=False,
                error="Draft ID is required.",
            )

        draft = self.gmail_service.get_draft(
            draft_id
        )

        return ExecutionResult(
            action=step.action,
            success=True,
            data=draft,
        )

    def _execute_email_draft_update(
        self,
        step: PlanStep,
    ) -> ExecutionResult:
        if self.gmail_service is None:
            return ExecutionResult(
                action=step.action,
                success=False,
                error="Gmail service is unavailable.",
            )

        draft_id = step.parameters.get(
            "draft_id"
        )
        recipient = step.parameters.get(
            "recipient"
        )
        subject = step.parameters.get(
            "subject"
        )
        body = step.parameters.get(
            "body"
        )

        if not (
            draft_id
            and recipient
            and subject
            and body
        ):
            return ExecutionResult(
                action=step.action,
                success=False,
                error=(
                    "Draft update requires "
                    "draft_id, recipient, subject, "
                    "and body."
                ),
            )

        draft = self.gmail_service.update_draft(
            draft_id=draft_id,
            to=recipient,
            subject=subject,
            body=body,
        )

        return ExecutionResult(
            action=step.action,
            success=True,
            data=draft,
        )

    def _execute_email_send(
        self,
        step: PlanStep,
    ) -> ExecutionResult:
        if self.gmail_service is None:
            return ExecutionResult(
                action=step.action,
                success=False,
                error="Gmail service is unavailable.",
            )

        draft_id = step.parameters.get(
            "draft_id"
        )

        if not draft_id:
            return ExecutionResult(
                action=step.action,
                success=False,
                error="Draft ID is required.",
            )

        result = self.gmail_service.send_draft(
            draft_id
        )

        return ExecutionResult(
            action=step.action,
            success=True,
            data=result,
        )    
