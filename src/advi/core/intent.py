from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class IntentType(str, Enum):
    CONVERSATION = "conversation"
    MEMORY_RETRIEVAL = "memory_retrieval"
    MEMORY_UPDATE = "memory_update"
    MEMORY_FORGET = "memory_forget"
    CAPABILITY_QUERY = "capability_query"
    IDENTITY_QUERY = "identity_query"
    INFORMATION_REQUEST = "information_request"
    SYSTEM_CONTROL = "system_control"

    TASK_CONFIRMATION = "task_confirmation"
    TASK_REJECTION = "task_rejection"
    TASK_MODIFICATION = "task_modification"
    TASK_PAUSE = "task_pause"
    TASK_RESUME = "task_resume"
    TASK_CANCEL = "task_cancel"
    TASK_READBACK = "task_readback"
    EMAIL_DRAFT_CREATE = "email_draft_create"
    EMAIL_READ = "email_read"
    EMAIL_DRAFT_UPDATE = "email_draft_update"
    EMAIL_SEND = "email_send"

    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Intent:
    type: IntentType
    confidence: float
    original_input: str
    target: str | None = None
    entities: dict[str, str] = field(
        default_factory=dict
    )
    parameters: dict[str, str] = field(
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