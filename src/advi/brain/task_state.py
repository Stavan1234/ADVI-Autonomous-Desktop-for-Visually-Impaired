from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any
import uuid

from advi.core.action_plan import ActionPlan, ExecutionResult


class TaskStatus(str, Enum):
    IDLE = "idle"
    IN_PROGRESS = "in_progress"
    AWAITING_INPUT = "awaiting_input"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ActiveTask:
    """
    First-class representation of an active, multi-turn task in ADVI.

    Preserves state across conversational interruptions and follow-up adjustments.
    Modifications ("make it more formal", "change the tone") update `revisions`
    and `context` rather than overwriting the original goal string.

    Field responsibilities:
      goal          – The original canonical user intent. Never modified once set.
      entities      – Structured domain parameters extracted at planning time
                      (recipient, subject, body, filename, url, …).
      context       – Runtime key/value store for temporary task state:
                      missing-info answers, confirmed sub-values, execution notes.
      revisions     – Ordered list of modification instructions from the user.
                      Applied on re-plan rather than mutating goal.
      plan          – Most recent ActionPlan generated for this task.
      results       – Execution results accumulated across all turns.
      waiting_for   – The name of the missing field currently blocking execution.
    """

    goal: str
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    status: TaskStatus = TaskStatus.IN_PROGRESS

    # Structured entities extracted from the goal (e.g. {"recipient": "Joel", "subject": "…"})
    entities: dict[str, Any] = field(default_factory=dict)

    # Temporary runtime context (missing-info answers, confirmed values, notes)
    context: dict[str, Any] = field(default_factory=dict)

    # Ordered modification requests from the user ("make it more formal", etc.)
    revisions: list[str] = field(default_factory=list)

    # Active plan and execution history
    plan: ActionPlan | None = None
    results: list[ExecutionResult] = field(default_factory=list)

    # Blocking field name when status == AWAITING_INPUT
    waiting_for: str | None = None

    # Exact plan fingerprint approved by the user. Invalidated by any task change.
    confirmation_fingerprint: str | None = None
    confirmation_issued_at: float | None = None
    confirmation_expires_at: float | None = None

    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    # ----------------------------------------------------------------
    # Mutation helpers
    # ----------------------------------------------------------------

    def apply_modification(self, instruction: str) -> None:
        """Record a user modification without changing the original goal."""
        self.revisions.append(instruction)
        self.updated_at = time.time()
        self.confirmation_fingerprint = None

    def supply_missing_info(self, field_name: str, value: Any) -> None:
        """
        Populate a missing field that was blocking execution.
        This is temporary task context – NOT a durable memory update.
        """
        self.context[field_name] = value
        # Also update entities so the re-planner can reference them
        self.entities[field_name] = value
        if self.waiting_for == field_name:
            self.waiting_for = None
            self.status = TaskStatus.IN_PROGRESS
        self.updated_at = time.time()

    def update_entities(self, updates: dict[str, Any]) -> None:
        """Merge new extracted entities into the task."""
        self.entities.update(updates)
        self.updated_at = time.time()

    def update_context(self, updates: dict[str, Any]) -> None:
        """Merge arbitrary runtime context values."""
        self.context.update(updates)
        self.confirmation_fingerprint = None
        self.updated_at = time.time()

    def set_awaiting_input(self, field_name: str) -> None:
        self.confirmation_fingerprint = None
        self.confirmation_issued_at = None
        self.confirmation_expires_at = None
        self.status = TaskStatus.AWAITING_INPUT
        self.waiting_for = field_name
        self.updated_at = time.time()

    def set_awaiting_confirmation(self, confirmation_details: str = "", confirmation_fingerprint: str | None = None, confirmation_issued_at: float | None = None, confirmation_expires_at: float | None = None) -> None:
        self.confirmation_fingerprint = confirmation_fingerprint
        self.confirmation_issued_at = confirmation_issued_at
        self.confirmation_expires_at = confirmation_expires_at
        self.status = TaskStatus.AWAITING_CONFIRMATION
        self.waiting_for = "confirmation"
        if confirmation_details:
            self.context["confirmation_details"] = confirmation_details
        self.updated_at = time.time()

    def mark_completed(self) -> None:
        self.confirmation_fingerprint = None
        self.confirmation_issued_at = None
        self.confirmation_expires_at = None
        self.status = TaskStatus.COMPLETED
        self.waiting_for = None
        self.updated_at = time.time()

    def mark_failed(self, reason: str = "") -> None:
        """Mark this task as permanently failed (not cancelled)."""
        self.confirmation_fingerprint = None
        self.confirmation_issued_at = None
        self.confirmation_expires_at = None
        self.status = TaskStatus.FAILED
        self.waiting_for = None
        if reason:
            self.context["failure_reason"] = reason
        self.updated_at = time.time()

    def mark_cancelled(self) -> None:
        self.confirmation_fingerprint = None
        self.confirmation_issued_at = None
        self.confirmation_expires_at = None
        self.status = TaskStatus.CANCELLED
        self.waiting_for = None
        self.updated_at = time.time()

    def build_effective_goal(self) -> str:
        """
        Produce the goal string for re-planning by combining the original goal,
        current entities/context values, and any accumulated revision instructions.
        """
        base = self.goal

        # Inject known entities so planner can use concrete values
        known: list[str] = []
        for k, v in self.entities.items():
            if v is not None:
                known.append(f"{k}={v!r}")
        # Also include context values that look like field answers
        for k, v in self.context.items():
            if k not in self.entities and v is not None and not k.startswith("_"):
                known.append(f"{k}={v!r}")

        if known:
            base = f"{base} [{', '.join(known)}]"

        if self.revisions:
            rev_str = "; ".join(self.revisions)
            base = f"{base} — modifications: {rev_str}"

        return base

    def to_dict(self) -> dict[str, Any]:
        last_error: str | None = None
        for r in reversed(self.results):
            if r.error:
                last_error = r.error
                break
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "entities": self.entities,
            "revisions": self.revisions,
            "status": self.status.value,
            "context": self.context,
            "waiting_for": self.waiting_for,
            "confirmation_bound": self.confirmation_fingerprint is not None,
            "action_count": len(self.plan.actions) if self.plan else 0,
            "result_count": len(self.results),
            "last_error": last_error,
        }
