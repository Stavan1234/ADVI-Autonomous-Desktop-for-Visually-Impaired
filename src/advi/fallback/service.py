from __future__ import annotations

import logging
from pathlib import Path

from ..providers import LLMProvider
from .action_plan_schema import ActionPlan
from .execution_loop import ExecutionLoop, ExecutionLoopResult
from .intent_schema import Intent
from .intent_service import IntentService
from .planner_service import PlannerService


logger = logging.getLogger(__name__)


class FallbackService:
    """
    Standalone agentic desktop fallback pipeline.

    Intent generation → action planning → execution.

    This service does not interact with ADVI's built-in
    planner, executor, or task coordinator.
    """

    def __init__(
        self,
        provider: LLMProvider,
        intent_prompt_path: str | Path,
        planner_prompt_path: str | Path,
        execution_loop: ExecutionLoop | None = None,
    ) -> None:
        self.intent_service = IntentService(
            provider=provider,
            prompt_path=intent_prompt_path,
        )

        self.planner_service = PlannerService(
            provider=provider,
            prompt_path=planner_prompt_path,
        )

        self.execution_loop = (
            execution_loop
            or ExecutionLoop()
        )

    def process(
        self,
        user_input: str,
    ) -> ExecutionLoopResult:
        logger.info(
            "Fallback processing request: %r",
            user_input,
        )

        intent = self.intent_service.extract_intent(
            user_input
        )

        logger.info(
            "Fallback intent: %s",
            intent.model_dump_json(),
        )

        if intent.missing_information:
            logger.info(
                "Fallback intent is missing information: %s",
                intent.missing_information,
            )

            return ExecutionLoopResult(
                success=False,
                results=[],
            )

        if intent.confirmation_required:
            logger.info(
                "Fallback intent requires confirmation."
            )

            return ExecutionLoopResult(
                success=False,
                results=[],
            )

        plan = self.planner_service.generate_plan(
            intent
        )

        logger.info(
            "Fallback action plan: %s",
            plan.model_dump_json(),
        )

        return self.execution_loop.run(
            plan
        )