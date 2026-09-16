from __future__ import annotations

import logging

from ..memory.long_term import LongTermMemory
from ..memory.retriever import MemoryRetriever
from .intent import Intent, IntentType
from .intent_detector import IntentDetector
from .memory_resolver import (
    MemoryOperation,
    MemoryResolver,
)


logger = logging.getLogger(__name__)


class IntentHandler:
    """Coordinates persistent-memory operations."""

    def __init__(
        self,
        detector: IntentDetector,
        memory_resolver: MemoryResolver,
        memory: LongTermMemory,
        retriever: MemoryRetriever | None = None,
    ) -> None:
        self.detector = detector
        self.memory_resolver = memory_resolver
        self.memory = memory
        self.retriever = retriever

    def handle(
        self,
        user_input: str,
        intent: Intent | None = None,
    ):
        """
        Handle a persistent-memory intent.

        An already-detected intent can be supplied so that
        ConversationEngine does not pay for a second intent call.
        """
        if intent is None:
            intent = self.detector.detect(
                user_input
            )

        if intent.type == IntentType.MEMORY_UPDATE:
            decision = self.memory_resolver.resolve(
                user_input
            )

            self._apply_memory_decision(
                decision
            )

            return intent, decision

        if intent.type == IntentType.MEMORY_FORGET:
            forgotten = self._forget_memory(
                user_input,
                intent,
            )

            return intent, forgotten

        return intent, None

    def _apply_memory_decision(
        self,
        decision,
    ) -> None:
        if decision.operation not in {
            MemoryOperation.CREATE,
            MemoryOperation.UPDATE,
        }:
            return

        if not (
            decision.category
            and decision.key
            and decision.value
            and decision.statement
        ):
            logger.warning(
                "Memory decision was incomplete; "
                "nothing was stored."
            )
            return

        self.memory.remember(
            category=decision.category,
            key=decision.key,
            value=decision.value,
            statement=decision.statement,
            confidence=decision.confidence,
        )

    def _forget_memory(
        self,
        user_input: str,
        intent: Intent | None = None,
    ) -> bool:
        """
        Forget an explicitly targeted memory when possible.

        Semantic search is only a fallback and requires a strong
        match because deletion is destructive.
        """
        if intent is not None and intent.target:
            exact = self.memory.recall(
                "user",
                intent.target,
            )

            if exact is not None:
                self.memory.forget(
                    exact.category,
                    exact.key,
                )
                return True

        if self.retriever is None:
            return False

        results = self.retriever.search(
            user_input,
            limit=5,
        )

        if not results:
            return False

        best = results[0]

        if best.score < 0.55:
            return False

        self.memory.forget(
            best.memory.category,
            best.memory.key,
        )

        return True