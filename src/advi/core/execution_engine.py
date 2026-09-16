from __future__ import annotations

import logging
from typing import Any

from advi.capabilities.desktop.context import DesktopContext
from advi.capabilities.registry import CapabilityRegistry, default_registry
from .action_plan import Action, ActionPlan, ExecutionResult, PlanStatus
from .action_contracts import validate_and_normalize_action
from .verification import ActionVerifier
from .execution_recovery import ExecutionObserver, ExecutionRecoveryPolicy, StepObservation
from .state_observation import StateObserver
from .failure_classification import FailureClassifier
from .execution_journal import ExecutionJournal

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """
    Unified Execution Interface for ADVI.

    Maintains a shared DesktopContext across all actions in a plan so that:
    - Window focus (HWND) survives between steps.
    - Chrome tab ownership (target_tab_id) is preserved across browse → search → click chains.
    - open_application results update the current_application for subsequent actions.

    Dispatches each action to its registered capability handler, runs verification,
    and returns standardised ExecutionResults.
    """

    def __init__(
        self,
        registry: CapabilityRegistry | None = None,
        verifier: ActionVerifier | None = None,
        context: DesktopContext | None = None,
        recovery_policy: ExecutionRecoveryPolicy | None = None,
        observer: ExecutionObserver | None = None,
        state_observer: StateObserver | None = None,
        max_retries_per_action: int = 1,
        failure_classifier: FailureClassifier | None = None,
        execution_journal: ExecutionJournal | None = None,
    ) -> None:
        self.registry = registry or default_registry
        self.verifier = verifier or ActionVerifier()
        # Shared execution context – survives across calls to execute_plan
        self.context = context or DesktopContext()
        self.recovery_policy = recovery_policy or ExecutionRecoveryPolicy()
        self.observer = observer
        self.state_observer = state_observer or StateObserver()
        self.max_retries_per_action = max(0, int(max_retries_per_action))
        self.failure_classifier = failure_classifier or FailureClassifier()
        self.execution_journal = execution_journal

    def execute_action(self, action: Action) -> ExecutionResult:
        """Execute a single atomic action after contract validation."""
        normalized, errors = validate_and_normalize_action(action)
        if errors:
            return ExecutionResult(
                action=action.action,
                success=False,
                error="Invalid action parameters: " + " ".join(errors),
                metadata={"validation_errors": errors},
            )
        if normalized is not None:
            action = normalized

        # Availability is runtime state, so refresh the owning capability when its
        # cached probe result is stale immediately before crossing the execution boundary.
        self.registry.refresh_for_action(action.action)
        capability = self.registry.get_capability_for_action(action.action)

        if not capability:
            logger.warning("No capability registered for action: %s", action.action)
            return ExecutionResult(
                action=action.action,
                success=False,
                error=f"No capability registered for action '{action.action}'.",
            )

        if not capability.is_available():
            logger.warning("Capability '%s' is currently unavailable.", capability.name)
            return ExecutionResult(
                action=action.action,
                success=False,
                error=f"Capability '{capability.name}' is currently unavailable.",
            )

        handler = capability.handler
        if not handler or not hasattr(handler, "execute"):
            logger.error("Capability '%s' has no valid execute handler.", capability.name)
            return ExecutionResult(
                action=action.action,
                success=False,
                error=f"Capability handler for '{capability.name}' is missing.",
            )

        # Inject the shared context into the handler if it accepts one
        if hasattr(handler, "context"):
            handler.context = self.context

        logger.info("Executing action '%s' via capability '%s'", action.action, capability.name)

        try:
            raw_result = handler.execute(action)
        except Exception as exc:
            logger.exception("Exception during execution of action '%s'", action.action)
            return ExecutionResult(
                action=action.action,
                success=False,
                error=f"Execution error: {exc}",
            )

        # Update focus context from successful action outcomes
        if raw_result.success:
            self._update_context_from_result(action, raw_result)

        # Verification
        verified_result = self.verifier.verify(action, raw_result)
        logger.info(
            "Action '%s' completed. Success=%s, Verified=%s",
            action.action,
            verified_result.success,
            verified_result.verified,
        )

        return verified_result

    def execute_plan(self, plan: ActionPlan, task_id: str | None = None) -> list[ExecutionResult]:
        """Execute a plan with bounded retry and post-step observation.

        The engine remains stop-on-failure: recovery may re-attempt the current safe step,
        but it never invents a new action sequence. This keeps execution authoritative and
        makes future brain-level replanning possible without coupling the executor to an LLM.
        """
        results: list[ExecutionResult] = []
        logger.info("Starting plan: '%s' (%d actions)", plan.goal, len(plan.actions))
        plan.status = PlanStatus.RUNNING

        self.context.reset()
        plan_fingerprint = ExecutionJournal.fingerprint_plan(plan.goal, plan.actions)

        for idx, action in enumerate(plan.actions, start=1):
            step_index = idx - 1
            if self.execution_journal is not None and task_id is not None:
                try:
                    self.execution_journal.begin(task_id, plan_fingerprint, step_index, action)
                except Exception:
                    logger.exception("Could not journal start of task step %s.", step_index)
            logger.info("Plan step %d/%d: %s", idx, len(plan.actions), action.action)

            if action.focus:
                self.context.set_application(action.focus)

            attempt = 0
            while True:
                before_state = self.state_observer.observe(
                    self.context, paths=self._observation_paths(action)
                )
                res = self.execute_action(action)
                attempt += 1
                after_state = self.state_observer.observe(
                    self.context, paths=self._observation_paths(action)
                )
                res = self.failure_classifier.annotate(action, res)
                res = res.model_copy(update={
                    "metadata": {
                        **res.metadata,
                        "state_before": before_state.to_dict(),
                        "state_after": after_state.to_dict(),
                    }
                })

                observation = StepObservation(
                    action=action.action,
                    success=res.success,
                    verified=res.verified,
                    error=res.error,
                    data=res.data,
                    context=self._context_snapshot(),
                )
                if self.observer is not None:
                    try:
                        self.observer.after_step(observation)
                    except Exception:  # observer must never break execution
                        logger.exception("Execution observer failed.")

                if res.success:
                    if attempt > 1:
                        res = res.model_copy(
                            update={
                                "metadata": {
                                    **res.metadata,
                                    "recovery_attempts": attempt - 1,
                                    "recovered": True,
                                }
                            }
                        )
                    results.append(res)
                    if self.execution_journal is not None and task_id is not None:
                        try:
                            self.execution_journal.finish(task_id, plan_fingerprint, step_index, res)
                        except Exception:
                            logger.exception("Could not journal completion of task step %s.", step_index)
                    break

                decision = self.recovery_policy.decide(
                    action,
                    res,
                    attempt=attempt,
                    max_retries=self.max_retries_per_action,
                )
                if not decision.retry:
                    logger.warning(
                        "Plan halted at step %d (%s): %s (%s)",
                        idx, action.action, res.error, decision.reason,
                    )
                    results.append(res)
                    if self.execution_journal is not None and task_id is not None:
                        try:
                            self.execution_journal.finish(task_id, plan_fingerprint, step_index, res)
                        except Exception:
                            logger.exception("Could not journal failed task step %s.", step_index)
                    plan.status = PlanStatus.FAILURE
                    return results

                logger.warning(
                    "Recovering step %d (%s): retry %d/%d (%s)",
                    idx, action.action, attempt, self.max_retries_per_action, decision.reason,
                )

                # Give the UI a moment to settle before repeating a transient-safe action.
                self.context.metadata["last_recovery_reason"] = decision.reason

            # Successful execution updates context after the final attempt.
            self._update_context_from_result(action, results[-1])

        plan.status = PlanStatus.SUCCESS
        logger.info("Plan completed successfully.")
        return results


    @staticmethod
    def _observation_paths(action: Action) -> list[str]:
        paths: list[str] = []
        for key in ("path", "filepath"):
            value = action.parameters.get(key)
            if value:
                paths.append(str(value))
        return paths

    def _context_snapshot(self) -> dict[str, Any]:
        """Return a small JSON-friendly observation of execution context."""
        return {
            "current_application": self.context.current_application,
            "target_hwnd": self.context.target_hwnd,
            "target_tab_id": self.context.target_tab_id,
            "target_tab_url": self.context.target_tab_url,
            "target_tab_title": self.context.target_tab_title,
            "metadata": dict(self.context.metadata),
        }

    def _update_context_from_result(self, action: Action, result: ExecutionResult) -> None:
        """Update shared context from successful action outcomes."""
        if action.action == "open_application":
            app = action.parameters.get("application") or action.target
            hwnd = result.metadata.get("hwnd")
            if app:
                self.context.set_application(str(app), hwnd=hwnd)

        elif action.action == "navigate":
            url = result.data or action.parameters.get("url")
            if url:
                self.context.target_tab_url = str(url)

        elif action.action == "focus_window":
            hwnd = result.metadata.get("hwnd") or (result.data if isinstance(result.data, int) else None)
            if hwnd:
                self.context.target_hwnd = int(hwnd)

