from __future__ import annotations

import logging
import re
from typing import Any

from advi.core.action_plan import Action, ExecutionResult
from advi.memory.long_term import LongTermMemory
from advi.memory.retriever import MemoryRetriever

logger = logging.getLogger(__name__)


class MemoryCapability:
    """
    Durable Memory Capability.
    Provides verified persistence, semantic search, and evidence retrieval over user facts
    via LongTermMemory (SQLite) and MemoryRetriever.
    """

    SUPPORTED_ACTIONS = {
        "memory_retrieval",
        "memory_update",
        "memory_forget",
    }

    def __init__(
        self,
        memory: LongTermMemory | None = None,
        retriever: MemoryRetriever | None = None,
    ) -> None:
        self.memory = memory
        self.retriever = retriever

    def is_available(self) -> bool:
        return self.memory is not None or self.retriever is not None

    def execute(self, action: Action) -> ExecutionResult:
        handler = getattr(self, f"_execute_{action.action}", None)
        if handler is None:
            return ExecutionResult(
                action=action.action,
                success=False,
                error=f"Unsupported memory action: {action.action}",
            )

        try:
            return handler(action)
        except Exception as exc:
            logger.exception("Memory action failed: %s", action.action)
            return ExecutionResult(
                action=action.action,
                success=False,
                error=str(exc),
            )

    def _execute_memory_retrieval(self, action: Action) -> ExecutionResult:
        query = str(action.parameters.get("query") or action.target or "").strip()
        if not query:
            return ExecutionResult(
                action=action.action,
                success=False,
                error="No query provided for memory retrieval.",
            )

        facts: list[str] = []

        # 1. Try hybrid semantic retrieval
        if self.retriever:
            try:
                retrieved = self.retriever.retrieve(query, limit=5)
                if retrieved:
                    facts.extend(retrieved)
            except Exception as exc:
                logger.warning("MemoryRetriever error: %s", exc)

        # 2. Fallback to direct SQLite lexical search if retriever empty or missing
        if not facts and self.memory:
            try:
                matches = self.memory.search(query, limit=5)
                facts = [m.statement for m in matches if m.statement]
            except Exception as exc:
                logger.warning("LongTermMemory search error: %s", exc)

        human_readable = (
            f"Found {len(facts)} relevant facts in memory."
            if facts
            else "No matching facts found in memory."
        )

        return ExecutionResult(
            action=action.action,
            success=True,
            data=facts,
            human_readable=human_readable,
            verified=True,
            metadata={"query": query, "count": len(facts)},
        )

    def _execute_memory_update(self, action: Action) -> ExecutionResult:
        fact = str(
            action.parameters.get("fact")
            or action.parameters.get("content")
            or action.parameters.get("value")
            or action.target
            or ""
        ).strip()

        if not fact:
            return ExecutionResult(
                action=action.action,
                success=False,
                error="No fact provided to store in memory.",
            )

        if not self.memory:
            return ExecutionResult(
                action=action.action,
                success=False,
                error="Long-term SQLite memory store is not available.",
            )

        category = str(action.parameters.get("category") or "user_fact").strip()
        key = str(action.parameters.get("key") or "").strip()

        # Derive a clean key if not explicitly given
        if not key:
            key_raw = re.sub(r"[^a-zA-Z0-9]+", "_", fact[:35]).strip("_").lower()
            key = key_raw or "general_fact"

        value = str(action.parameters.get("value") or fact).strip()

        # 1. Perform actual write to SQLite
        try:
            self.memory.remember(
                category=category,
                key=key,
                value=value,
                statement=fact,
            )
        except Exception as exc:
            logger.exception("Failed to write memory to SQLite: %s", exc)
            return ExecutionResult(
                action=action.action,
                success=False,
                error=f"Database write error: {exc}",
            )

        # 2. Verify write actually occurred in SQLite
        verified_memory = self.memory.recall(category=category, key=key)
        if not verified_memory:
            return ExecutionResult(
                action=action.action,
                success=False,
                error="Memory write failed verification; record not found in database.",
                verified=False,
            )

        # 3. Refresh retriever cache so new memory is immediately retrievable
        if self.retriever:
            try:
                self.retriever.refresh()
            except Exception as exc:
                logger.warning("Could not refresh retriever cache: %s", exc)

        return ExecutionResult(
            action=action.action,
            success=True,
            data={"category": category, "key": key, "statement": fact},
            human_readable=f"Remembered: '{fact}'.",
            verified=True,
            verification_details={"id": verified_memory.id, "category": category, "key": key},
            metadata={"category": category, "key": key},
        )

    def _execute_memory_forget(self, action: Action) -> ExecutionResult:
        target = str(
            action.parameters.get("fact")
            or action.parameters.get("key")
            or action.target
            or ""
        ).strip()

        if not target:
            return ExecutionResult(
                action=action.action,
                success=False,
                error="No target fact or key specified to forget.",
            )

        if not self.memory:
            return ExecutionResult(
                action=action.action,
                success=False,
                error="Long-term SQLite memory store is not available.",
            )

        category = str(action.parameters.get("category") or "").strip()
        key = str(action.parameters.get("key") or "").strip()

        deleted_count = 0

        # If category and key are explicitly provided
        if category and key:
            self.memory.forget(category=category, key=key)
            deleted_count = 1
        else:
            # Search for matching memories to forget
            matches = self.memory.search(target, limit=5)
            for m in matches:
                self.memory.forget(category=m.category, key=m.key)
                deleted_count += 1

        if deleted_count == 0:
            return ExecutionResult(
                action=action.action,
                success=False,
                error=f"No matching memory found to forget for target '{target}'.",
                verified=False,
            )

        # Refresh retriever cache
        if self.retriever:
            try:
                self.retriever.refresh()
            except Exception:
                pass

        return ExecutionResult(
            action=action.action,
            success=True,
            data=target,
            human_readable=f"Removed {deleted_count} record(s) matching '{target}' from memory.",
            verified=True,
            metadata={"deleted_count": deleted_count},
        )
