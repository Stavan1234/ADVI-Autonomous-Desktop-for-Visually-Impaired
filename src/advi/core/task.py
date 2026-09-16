from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    AWAITING_INPUT = "awaiting_input"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    AWAITING_INPUT = "awaiting_input"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TaskStepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ConfirmationStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


@dataclass
class ConfirmationRequest:
    action: str
    summary: str
    status: ConfirmationStatus = (
        ConfirmationStatus.PENDING
    )


@dataclass
class TaskStepState:
    action: str
    status: TaskStepStatus = TaskStepStatus.PENDING
    result: Any = None
    error: str | None = None


@dataclass
class Task:
    task_id: str
    status: TaskStatus = TaskStatus.PENDING

    steps: list[TaskStepState] = field(
        default_factory=list
    )

    current_step: int = 0

    context: dict[str, str] = field(
        default_factory=dict
    )

    confirmation: ConfirmationRequest | None = None

    error: str | None = None