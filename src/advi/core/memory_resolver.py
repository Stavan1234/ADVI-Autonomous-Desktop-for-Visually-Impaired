from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum

from ..memory.long_term import LongTermMemory
from ..providers import LLMProvider
from .llm_telemetry import LLMTelemetry


logger = logging.getLogger(__name__)


class MemoryOperation(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    KEEP = "keep"
    IGNORE = "ignore"


@dataclass(frozen=True)
class MemoryDecision:
    operation: MemoryOperation
    category: str | None
    key: str | None
    value: str | None
    statement: str | None
    confidence: float
    reason: str = ""
    entities: dict[str, str] = field(
        default_factory=dict
    )

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


class MemoryResolver:
    """Resolve a memory-update request against relevant existing memory."""

    def __init__(
        self,
        provider: LLMProvider,
        memory: LongTermMemory,
        telemetry: LLMTelemetry | None = None,
    ) -> None:
        self.provider = provider
        self.memory = memory
        self.telemetry = telemetry

    def resolve(
        self,
        user_input: str,
    ) -> MemoryDecision:
        text = user_input.strip()

        if not text:
            return self._ignore(
                "Empty memory request."
            )

        existing = self.memory.search(
            text,
            limit=8,
        )

        context_lines = []

        for item in existing:
            context_lines.append(
                f"- category={item.category}; "
                f"key={item.key}; "
                f"value={item.value}; "
                f"statement={item.statement}; "
                f"confidence={item.confidence:.2f}"
            )

        existing_context = (
            "\n".join(context_lines)
            if context_lines
            else "(no relevant existing memories)"
        )

        prompt = f"""
Resolve the user's memory request.

The user is asking ADVI to remember or change information.

Your job is NOT to answer the user.

Determine:

1. What durable fact the user wants stored.
2. Whether it should CREATE a new memory,
   UPDATE an existing memory,
   KEEP an existing memory,
   or IGNORE the request.
3. The appropriate category and key.
4. A concise factual retrieval statement.
5. Your confidence.

Allowed operations:

- create
- update
- keep
- ignore

Use CREATE when the information is genuinely new.

Use UPDATE when the user clearly changes or corrects
an existing fact.

Use KEEP when the requested information is already
consistent with an existing memory and no change is needed.

Use IGNORE when the information is temporary, unclear,
not durable, or should not be stored.

Relevant existing memories:

{existing_context}

User request:

{text}

Return ONLY valid JSON:

{{
  "operation": "create|update|keep|ignore",
  "category": "user|preference|project|family|education|other|null",
  "key": "short_key_or_null",
  "value": "durable_value_or_null",
  "statement": "short factual retrieval statement or null",
  "confidence": 0.0,
  "reason": "short explanation",
  "entities": {{}}
}}

Rules:

- Never invent facts.
- Do not store assumptions.
- Do not turn temporary conversation into permanent memory.
- Preserve the user's meaning.
- If an existing memory clearly represents the same fact,
  use its category and key.
- If the user explicitly corrects an existing fact,
  prefer UPDATE.
- If uncertain, use IGNORE rather than inventing memory.
""".strip()

        try:
            result = self.provider.chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "You are ADVI's memory resolution "
                            "component. Return only valid JSON."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ]
            )

            if self.telemetry is not None:
                self.telemetry.record(
                    result,
                    "memory_resolution",
                )

            return self._parse(result.text)

        except Exception:
            logger.exception(
                "Memory resolution failed."
            )

            return self._ignore(
                "Memory resolution failed."
            )

    @staticmethod
    def _parse(
        text: str,
    ) -> MemoryDecision:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return MemoryResolver._ignore(
                "Invalid resolver response."
            )

        raw_operation = str(
            data.get("operation", "ignore")
        ).strip().lower()

        try:
            operation = MemoryOperation(
                raw_operation
            )
        except ValueError:
            operation = MemoryOperation.IGNORE

        category = MemoryResolver._optional_string(
            data.get("category")
        )

        key = MemoryResolver._optional_string(
            data.get("key")
        )

        value = MemoryResolver._optional_string(
            data.get("value")
        )

        statement = MemoryResolver._optional_string(
            data.get("statement")
        )

        reason = (
            str(data.get("reason", "")).strip()
        )

        try:
            confidence = float(
                data.get("confidence", 0.0)
            )
        except (TypeError, ValueError):
            confidence = 0.0

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

        if operation in {
            MemoryOperation.CREATE,
            MemoryOperation.UPDATE,
        }:
            if not (
                category
                and key
                and value
                and statement
            ):
                return MemoryResolver._ignore(
                    "Memory mutation was incomplete."
                )

        return MemoryDecision(
            operation=operation,
            category=category,
            key=key,
            value=value,
            statement=statement,
            confidence=confidence,
            reason=reason,
            entities=entities,
        )

    @staticmethod
    def _optional_string(
        value,
    ) -> str | None:
        if value is None:
            return None

        text = str(value).strip()

        return text or None

    @staticmethod
    def _ignore(
        reason: str,
    ) -> MemoryDecision:
        return MemoryDecision(
            operation=MemoryOperation.IGNORE,
            category=None,
            key=None,
            value=None,
            statement=None,
            confidence=0.0,
            reason=reason,
        )