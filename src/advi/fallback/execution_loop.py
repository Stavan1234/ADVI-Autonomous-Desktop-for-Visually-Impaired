from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .action_plan_schema import ActionPlan
from .execution_context import ExecutionContext
from .executor import ActionResult, FallbackExecutor
from .perception import ScreenPerception

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExecutionLoopResult:
    success: bool
    results: list[ActionResult]
    metadata: dict[str, Any] = field(default_factory=dict)


class ExecutionLoop:
    """
    Execute a fallback action plan in one continuous run.

    Key Requirements & Architecture:
    1. Target Ownership: Maintains persistent ExecutionContext (target_tab_id, target_hwnd,
       current_application) across the entire plan.
    2. Continuous Execution: Keeps execution attached to the target Chrome tab/window
       without losing focus or jumping between tabs.
    3. State Awareness & Idempotency: Inspects state before retrying or re-executing actions.
    4. Structured Logging: Logs detailed execution info (action, target, focus, success, error, attempt).
    """

    def __init__(
        self,
        perception: ScreenPerception | None = None,
        executor: FallbackExecutor | None = None,
        context: ExecutionContext | None = None,
    ) -> None:
        self.perception = perception or ScreenPerception()
        self.context = context or ExecutionContext()
        self.executor = executor or FallbackExecutor(context=self.context)

    @property
    def current_application(self) -> str | None:
        return self.context.current_application

    @current_application.setter
    def current_application(self, value: str | None) -> None:
        self.context.current_application = value

    def run(self, plan: ActionPlan) -> ExecutionLoopResult:
        results: list[ActionResult] = []

        # Reset execution context for every new plan
        self.context.reset()

        total_actions = len(plan.actions)
        logger.info("Starting ExecutionLoop for plan with %d actions.", total_actions)

        for index, action in enumerate(plan.actions, start=1):
            logger.info("=" * 60)
            logger.info(
                "Action #%d/%d: action=%r | focus=%r | parameters=%s",
                index,
                total_actions,
                action.action,
                action.focus,
                action.parameters,
            )

            result = self._execute_action(action)
            results.append(result)

            logger.info(
                "Result Action #%d (%s): success=%s | data=%r | error=%r",
                index,
                action.action,
                result.success,
                result.data,
                result.error,
            )

            if not result.success:
                logger.warning("ExecutionLoop stopped at Action #%d (%s): %s", index, action.action, result.error)
                return ExecutionLoopResult(
                    success=False,
                    results=results,
                    metadata={"failed_action_index": index, "failed_action": action.action},
                )

            self._update_context(action)

        logger.info("ExecutionLoop completed successfully.")
        return ExecutionLoopResult(
            success=True,
            results=results,
            metadata={"total_actions": total_actions},
        )

    def _ensure_current_application_focus(self, action_name: str) -> ActionResult | None:
        """
        Ensure application focus context is active.
        """
        if action_name in {"open_application", "finish"}:
            return None

        if not self.context.current_application:
            return None

        logger.info("Ensuring foreground application context: %s", self.context.current_application)
        self.executor.ensure_application_focus(self.context.current_application)
        return None

    def _execute_action(self, action: Any) -> ActionResult:
        # Update focus context if explicitly provided
        action_focus = getattr(action, "focus", None)
        if action_focus:
            requested_focus = str(action_focus).strip()
            if requested_focus:
                self.context.set_application(requested_focus)

        # 1. Restore OS focus when necessary for non-CDP actions
        focus_error = self._ensure_current_application_focus(action.action)
        if focus_error is not None:
            return focus_error

        parameters = dict(action.parameters)
        target = parameters.get("target")

        # 2. Web actions targeting an active Chrome CDP tab: CDP executes directly in-page
        if self.context.is_chrome_target() and action.action in {"search", "navigate", "click"}:
            return self.executor.execute_action(action, context=self.context)

        # 3. Actions without UI target
        if not target:
            return self.executor.execute_action(action, context=self.context)

        target_string = str(target).strip()
        if not target_string:
            return ActionResult(
                action=action.action,
                success=False,
                error="Target parameter was empty.",
            )

        # 4. Perception target resolution for desktop / UIA / Vision targets
        logger.info("Resolving perception target %r for action %r in app %r", target_string, action.action, self.context.current_application)
        perception_result = self.perception.find(
            target=target_string,
            action=action.action,
            application=self.context.current_application,
        )

        if not perception_result.found:
            return ActionResult(
                action=action.action,
                success=False,
                error=perception_result.error or f"Target {target_string!r} could not be resolved.",
            )

        # Restore focus again after perception (perception captures screenshots / inspects windows)
        focus_error = self._ensure_current_application_focus(action.action)
        if focus_error is not None:
            return focus_error

        parameters["resolved_target"] = perception_result.target
        action = action.model_copy(update={"parameters": parameters})

        return self.executor.execute_action(action, context=self.context)

    def _update_context(self, action: Any) -> None:
        """Update context state following successful action execution."""
        if action.action == "open_application":
            app = action.parameters.get("application")
            if app:
                self.context.set_application(str(app).strip())