"""
Canonical production data contracts for ADVI action planning and execution.

Derived from actual usage across:
- brain/agent.py (generates plans, reads results)
- fallback/planner_service.py (generates plans with action/target/focus/reason)
- fallback/executor.py (ActionResult shape)
- fallback/execution_loop.py (action.focus, action.parameters)
- capabilities/*/executor.py (ExecutionResult fields)
"""
from __future__ import annotations

import time
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, ConfigDict


# ---------------------------------------------------------------------------
# Status enumerations
# ---------------------------------------------------------------------------

class VerificationStatus(str, Enum):
    """Evidence state for an executed action."""
    VERIFIED = "verified"
    FAILED = "failed"
    UNCERTAIN = "uncertain"


class PlanStatus(str, Enum):
    """Lifecycle status of an ActionPlan."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# Action – one atomic instruction in a plan
# ---------------------------------------------------------------------------

class Action(BaseModel):
    """
    A single executable instruction.

    Fields derived from actual producers:
    - agent._generate_action_plan: action, target, parameters, focus
    - fallback/planner_service: action, target, focus, parameters, reason
    - fallback/executor: action.parameters, action.focus, action.action
    - capabilities/*/executor: action.target, action.parameters
    """
    model_config = ConfigDict(extra="allow")

    # Core (required by all producers)
    action: str

    # Optional context fields used by planner and execution loop
    target: str | None = None       # semantic UI target (window title, element label)
    focus: str | None = None        # application context for this action
    reason: str | None = None       # why this action is in the plan (PlannerService)
    parameters: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# ActionPlan – ordered sequence of actions for a user goal
# ---------------------------------------------------------------------------

class ActionPlan(BaseModel):
    """
    Complete plan for achieving a user goal.

    Fields derived from actual producers:
    - agent._generate_action_plan: goal, actions, missing_information,
      confirmation_required, confirmation_prompt
    - fallback/planner_service.generate_plan: actions, reason
    """
    model_config = ConfigDict(extra="allow")

    goal: str = ""
    actions: list[Action] = Field(default_factory=list)
    status: PlanStatus = PlanStatus.PENDING

    # Planning metadata
    reason: str | None = None
    missing_information: list[str] = Field(default_factory=list)
    confirmation_required: bool = False
    confirmation_prompt: str = ""

    created_at: float = Field(default_factory=time.time)


# ---------------------------------------------------------------------------
# ExecutionResult – outcome of executing a single Action
# ---------------------------------------------------------------------------

class ExecutionResult(BaseModel):
    """
    Standardized result returned by every capability executor.

    Fields derived from actual consumers:
    - execution_engine: action, success, error, verified
    - agent._author_grounded_response: success, human_readable, action, error
    - agent (memory path): data
    - verification.py: verified, verification_details, metadata
    - context.py (previous_action_results): action, success, human_readable, error
    - capabilities/*/executor: data, human_readable, verified,
      verification_details, metadata
    """
    model_config = ConfigDict(extra="allow")

    # Core
    action: str
    success: bool

    # Output payload
    data: Any = None
    human_readable: str | None = None

    # Failure information
    error: str | None = None

    # Verification state (populated by ActionVerifier, not by executors)
    verified: bool = False
    verification_status: VerificationStatus = VerificationStatus.UNCERTAIN
    verification_details: dict[str, Any] = Field(default_factory=dict)

    # Arbitrary capability-specific metadata
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Timing
    executed_at: float = Field(default_factory=time.time)

