from __future__ import annotations

import json
import logging
import re
from typing import Any

from advi.capabilities.registry import CapabilityRegistry, default_registry
from advi.core.action_plan import Action, ActionPlan, ExecutionResult, PlanStatus, VerificationStatus
from advi.core.execution_engine import ExecutionEngine
from advi.core.replanning import ReplanningEngine
from advi.core.goal_verification import GoalVerifier, GoalVerificationStatus
from advi.core.capability_policy import CapabilityPolicy, PolicyDisposition
from advi.core.confirmation import ConfirmationManager
from advi.core.personality import build_advi_system_prompt
from advi.io.output import AdviResponse
from advi.io.terminal_trace import TerminalTraceRenderer
from advi.memory.retriever import MemoryRetriever
from advi.memory.session import SessionBuffer
from advi.memory.short_term import ShortTermMemory
from advi.providers import LLMProvider
from .context import AgentContext
from .conversation_state import ConversationState
from .fallback_gateway import FallbackGateway
from .fallback_policy import FallbackPolicy
from .reference_resolution import ConversationReferenceResolver
from .followup_semantics import FollowUpSemantics
from advi.core.failure_classification import FailureClass
from advi.core.task_persistence import TaskPersistence
from advi.core.execution_journal import ExecutionJournal
from advi.core.research_synthesis import ResearchSynthesizer
from advi.core.research_evidence import ResearchEvidenceStore
from advi.core.diagnostics import DiagnosticsCollector
from advi.core.health import ADVIHealthChecker
from .reasoning import ReasoningEngine
from .planner import PlannerEngine, PlanningHints
from .task_state import ActiveTask, TaskStatus

logger = logging.getLogger(__name__)



class ADVIAgent:
    """
    Unified Cognitive Brain of ADVI.
    Combines context assembly, intelligent intent routing, first-class multi-turn task tracking,
    authoritative execution dispatch, and grounded natural responses.
    """

    def __init__(
        self,
        provider: LLMProvider,
        execution_engine: ExecutionEngine | None = None,
        registry: CapabilityRegistry | None = None,
        short_term_memory: ShortTermMemory | None = None,
        session_buffer: SessionBuffer | None = None,
        retriever: MemoryRetriever | None = None,
        previous_session_context: str | None = None,
        fallback_gateway: FallbackGateway | None = None,
        task_persistence: TaskPersistence | None = None,
        execution_journal: ExecutionJournal | None = None,
        resume_task: bool = True,
        research_evidence_store: ResearchEvidenceStore | None = None,
        runtime: Any | None = None,
    ) -> None:
        self.provider = provider
        self.runtime = runtime
        self.registry = registry or default_registry
        self.capability_policy = CapabilityPolicy(self.registry)
        self.confirmation_manager = ConfirmationManager()
        self.execution_engine = execution_engine or ExecutionEngine(registry=self.registry)
        self.short_term_memory = short_term_memory or ShortTermMemory()
        self.session_buffer = session_buffer or SessionBuffer()
        self.retriever = retriever
        self.previous_session_context = previous_session_context
        self.conversation_state = ConversationState()
        self.fallback_gateway = fallback_gateway
        self.task_persistence = task_persistence
        self.execution_journal = execution_journal
        self.research_evidence_store = research_evidence_store
        if self.research_evidence_store is None and task_persistence is not None:
            try:
                self.research_evidence_store = ResearchEvidenceStore(task_persistence.database_path)
            except Exception as exc:
                logger.warning("Could not initialize research evidence store: %s", exc)
        self.fallback_policy = FallbackPolicy()
        self.replanner = ReplanningEngine(provider, max_replans=2)
        self.goal_verifier = GoalVerifier()
        self.research_synthesizer = ResearchSynthesizer(provider, self.research_evidence_store)
        self.planner = PlannerEngine(provider, self.registry)
        self.reference_resolver = ConversationReferenceResolver()
        self.followup_semantics = FollowUpSemantics()
        self.diagnostics_collector = DiagnosticsCollector()
        self.health_checker = ADVIHealthChecker()
        self.terminal_trace = TerminalTraceRenderer()
        self._turn_decision = None
        self._turn_plan = None
        self._turn_results: list[ExecutionResult] = []
        self.reasoner = ReasoningEngine(
            provider,
            fallback_available=lambda: bool(self.fallback_gateway and self.fallback_gateway.available()),
        )
        if resume_task and self.task_persistence is not None:
            try:
                resumed = self.task_persistence.latest_resumable()
                if resumed is not None:
                    self._mark_interrupted_task(resumed)
                    self.conversation_state.set_task(resumed)
                    self.conversation_state.resumed_task = True
                    logger.info("Resumed persisted task %s: %s", resumed.task_id, resumed.goal)
            except Exception as exc:
                logger.warning("Could not resume persisted task: %s", exc)

    @property
    def active_task(self) -> ActiveTask | None:
        """Compatibility view of the current conversational work item."""
        return self.conversation_state.current_task

    @active_task.setter
    def active_task(self, task: ActiveTask | None) -> None:
        previous = self.conversation_state.current_task
        if task is None:
            if previous is not None and self.task_persistence is not None:
                try:
                    self.task_persistence.save(previous)
                except Exception as exc:
                    logger.warning("Task persistence failed for %s: %s", previous.task_id, exc)
            self.conversation_state.clear_current_task(archive=True)
        else:
            self.conversation_state.set_task(task)
            if self.task_persistence is not None:
                try:
                    self.task_persistence.save(task)
                except Exception as exc:
                    logger.warning("Task persistence failed for %s: %s", task.task_id, exc)

    def diagnostics(self) -> dict[str, Any]:
        """Return a bounded, read-only runtime snapshot for debugging."""
        return self.diagnostics_collector.capture(self).to_dict()

    def health(self, *, refresh_capabilities: bool = False) -> dict[str, Any]:
        """Return a read-only runtime health report.

        Capability refresh is opt-in so merely inspecting health does not
        repeatedly invoke environment/authentication probes.
        """
        return self.health_checker.check(self, refresh_capabilities=refresh_capabilities).to_dict()

    def get_session_messages(self) -> list[dict[str, str]]:
        """Return the raw messages for session consolidation."""
        return list(self.session_buffer.messages)

    def get_session_buffer(self) -> list[dict[str, str]]:
        """Compatibility alias for session consolidation."""
        return self.get_session_messages()

    def respond(self, user_input: str) -> AdviResponse:
        """Process one user turn through the complete cognitive cycle."""
        text = user_input.strip()
        if not text:
            return AdviResponse("I'm listening. How can I help you?")

        logger.info("ADVIAgent processing turn: %r", text)
        self._turn_decision = None
        self._turn_plan = None
        self._turn_results = []

        # Refresh dynamic capability state before reasoning so the model sees the
        # environment as it exists now, not only when the process started.
        try:
            self.registry.refresh_stale()
        except Exception:
            logger.exception("Dynamic capability refresh failed before turn.")

        # 1. Assemble bounded context
        context = self._assemble_context(text)

        resolution = self.reference_resolver.resolve(text, context)
        context.resolved_references = [{"kind": r.kind, "value": r.value, "source_id": r.source_id, "label": r.label, "confidence": r.confidence, "metadata": r.metadata} for r in resolution.references]
        if resolution.needs_clarification:
            reply = resolution.clarification or "I need more detail before I continue."
            self._record_turn(text, reply)
            return AdviResponse(reply)
        routed_text = resolution.normalized_message or text

        # Deterministic follow-up semantics run before LLM routing. They convert
        # common conversational edits into explicit task updates, while leaving
        # the natural-language turn intact for planning.
        followup = self.followup_semantics.interpret(text, context)
        if followup.kind == "modify" and self.active_task:
            self.active_task.apply_modification(followup.task_update or text)
            if followup.field and followup.value:
                self.active_task.update_entities({followup.field: followup.value})
            self.active_task.status = TaskStatus.IN_PROGRESS
            response = self._plan_and_execute_task(
                self.active_task.build_effective_goal(), context, existing_task=self.active_task
            )
        elif followup.kind == "resume" and self.active_task:
            response = self._route_and_process("continue", context, bypass_followup=True)
        else:
            # 2. Understand intent and route cognitive path using LLM reasoning
            response = self._route_and_process(routed_text, context)

        # 3. Record turn history
        self._persist_current_task()
        self._record_turn(text, response.text)
        self._persist_current_task()
        try:
            self.terminal_trace.render(
                user_input=text,
                decision=self._turn_decision,
                plan=self._turn_plan,
                results=self._turn_results,
                response=response.text,
                task_status=(self.active_task.status.value if self.active_task else None),
            )
        except Exception:
            logger.exception("Terminal trace rendering failed.")
        return response

    def _assemble_context(self, user_message: str) -> AgentContext:
        """Gather relevant memory, bounded recent history, active task state, and capabilities."""
        recent = self.short_term_memory.get_messages()[-6:]

        # Retrieve relevant long-term memories
        relevant_memories: list[str] = []
        if self.retriever:
            try:
                retrieved = self.retriever.retrieve(user_message, limit=5)
                if retrieved:
                    relevant_memories = (
                        retrieved if isinstance(retrieved, list) else [str(retrieved)]
                    )
            except Exception as exc:
                logger.warning("Memory retrieval failed: %s", exc)

        # Surface execution results: active task first, fall back to session ring
        result_source = (
            self.active_task.results[-5:]
            if self.active_task and self.active_task.results
            else [ExecutionResult(**r) for r in self.conversation_state.recent_results[-5:] if isinstance(r, dict) and "action" in r and "success" in r]
        )
        previous_action_results: list[dict] = [
            {
                "action": r.action,
                "success": r.success,
                "verified": r.verified,
                "human_readable": r.human_readable,
                "error": r.error,
            }
            for r in result_source
        ]

        identity_prompt = build_advi_system_prompt()
        if self.previous_session_context:
            identity_prompt = (
                identity_prompt
                + "\n\n### Previous Session Summary:\n"
                + self.previous_session_context
            )

        return AgentContext(
            current_message=user_message,
            recent_history=recent,
            relevant_memories=relevant_memories,
            active_task=self.active_task.to_dict() if self.active_task else None,
            recent_tasks=[t.to_dict() for t in self.conversation_state.recent_tasks[-3:]],
            previous_action_results=previous_action_results,
            recent_research=self._recent_research_context(),
            available_capabilities=self.registry.summary_for_prompt(),
            identity_prompt=identity_prompt,
            pending_confirmation=bool(
                self.active_task and self.active_task.status == TaskStatus.AWAITING_CONFIRMATION
            ),
        )

    def _route_and_process(self, text: str, context: AgentContext, bypass_followup: bool = False) -> AdviResponse:
        """Route a turn from one broad reasoning decision; execution remains authoritative in Python."""
        decision = self.reasoner.decide(text, context)
        self._turn_decision = decision
        logger.info(
            "Reasoning decision: mode=%s action=%s confidence=%.2f reason=%s",
            decision.mode, decision.action, decision.confidence, decision.reason,
        )

        if decision.mode == "task_confirm" and self.active_task and self.active_task.status == TaskStatus.AWAITING_CONFIRMATION:
            plan = self.active_task.plan
            fingerprint = self.active_task.confirmation_fingerprint
            valid = bool(
                plan
                and self.confirmation_manager.validate(
                    plan,
                    fingerprint,
                    issued_at=self.active_task.confirmation_issued_at,
                    expires_at=self.active_task.confirmation_expires_at,
                )
            )
            if valid and self.confirmation_manager.consume(fingerprint):
                self.active_task.confirmation_fingerprint = None
                self.active_task.confirmation_issued_at = None
                self.active_task.confirmation_expires_at = None
                return self._execute_active_task()
            # A stale approval must never authorize a changed plan.
            self.active_task.confirmation_fingerprint = None
            self.active_task.confirmation_issued_at = None
            self.active_task.confirmation_expires_at = None
            self.active_task.status = TaskStatus.IN_PROGRESS
            return AdviResponse("The requested action changed, so the previous confirmation is no longer valid. Please confirm the updated action again.")

        if decision.mode == "task_cancel" and self.active_task:
            self.active_task.mark_cancelled()
            self.active_task = None
            return AdviResponse("Understood. I have cancelled that task.")

        if (
            self.active_task
            and self.active_task.status == TaskStatus.AWAITING_INPUT
            and self.active_task.waiting_for == "interrupted_execution_review"
        ):
            if decision.mode == "task_cancel":
                self.active_task.mark_cancelled()
                self.active_task = None
                return AdviResponse("Understood. I cancelled the interrupted task without repeating the unfinished action.")
            if decision.mode == "task_resume":
                interrupted = self.active_task.context.get("_interrupted_step", {})
                action_name = interrupted.get("action", "the last action")
                self.active_task.context.pop("_interrupted_step", None)
                self.active_task.waiting_for = None
                self.active_task.status = TaskStatus.IN_PROGRESS
                return self._plan_and_execute_task(
                    self.active_task.build_effective_goal(),
                    context,
                    existing_task=self.active_task,
                )
            return AdviResponse(
                "The application was interrupted while I was executing "
                f"'{self.active_task.context.get('_interrupted_step', {}).get('action', 'an action')}'. "
                "I will not repeat it automatically. Say 'continue' to reassess the task from its current state, or 'cancel' to stop."
            )

        if decision.mode == "task_modify" and self.active_task:
            self.active_task.apply_modification(decision.task_update or text)
            self.active_task.status = TaskStatus.IN_PROGRESS
            return self._plan_and_execute_task(self.active_task.build_effective_goal(), context, existing_task=self.active_task)

        if self.active_task and self.active_task.status == TaskStatus.AWAITING_INPUT:
            field_name = self.active_task.waiting_for or "value"
            self.active_task.supply_missing_info(field_name, text)
            return self._plan_and_execute_task(self.active_task.build_effective_goal(), context, existing_task=self.active_task)

        if decision.mode == "task_resume" and self.active_task:
            return self._plan_and_execute_task(self.active_task.build_effective_goal(), context, existing_task=self.active_task)

        if decision.mode == "research_followup":
            return self._answer_research_followup(text, decision.references.get("research_query") if decision.references else None)

        if decision.mode == "memory_query":
            query = decision.memory_query or text
            res = self._execute_authorized_action(
                Action(action="memory_retrieval", parameters={"query": query})
            )
            return self._answer_memory_query(query, res.data or [], context)

        if decision.mode == "memory_update":
            fact = decision.memory_fact or text
            fact_clean = re.sub(r"^(please\s+)?remember\s+that\s+", "", fact, flags=re.IGNORECASE).strip()
            res = self._execute_authorized_action(
                Action(action="memory_update", parameters={"fact": fact_clean})
            )
            if not res.success:
                return AdviResponse(res.human_readable or res.error or "I could not update memory.")
            return AdviResponse(f"I will remember that {fact_clean}.")

        if decision.mode == "memory_forget":
            target = decision.memory_fact or text
            target_clean = re.sub(r"^(please\s+)?forget\s+that\s+", "", target, flags=re.IGNORECASE).strip()
            action = Action(action="memory_forget", parameters={"fact": target_clean})
            policy = self.capability_policy.evaluate_action(action)
            if policy.disposition == PolicyDisposition.DENY:
                return AdviResponse(f"I cannot forget that memory with the current capabilities.")
            if policy.disposition == PolicyDisposition.CONFIRM:
                task = ActiveTask(goal=f"Forget memory: {target_clean}")
                task.plan = ActionPlan(goal=task.goal, actions=[action], reason="User requested durable memory deletion.")
                confirmation = self.confirmation_manager.issue(task.plan)
                task.set_awaiting_confirmation(
                    confirmation.prompt or "Please confirm before I forget that memory.",
                    confirmation.fingerprint,
                    confirmation.issued_at,
                    confirmation.expires_at,
                )
                self.active_task = task
                return AdviResponse(f"{confirmation.prompt or 'Please confirm before I forget that memory.'} (Please reply yes or no)")
            res = self.execution_engine.execute_action(action)
            return AdviResponse(res.human_readable or res.error or f"I could not forget {target_clean}.")

        if decision.mode == "fallback":
            if self.fallback_gateway and self.fallback_gateway.available():
                outcome = self.fallback_gateway.process(text, reason=decision.fallback_reason or decision.reason)
                if outcome.success:
                    return AdviResponse(outcome.text or "Done.")
                logger.warning("Fallback route failed: %s", outcome.reason)

        if decision.mode == "action":
            response = self._plan_and_execute_task(
                decision.goal or text,
                context,
                planning_hints=PlanningHints(
                    preferred_action=decision.action,
                    reason=decision.reason,
                    references=decision.references,
                ),
            )
            # A missing primary plan is an explicit unavailable-capability signal.
            if not self.active_task or self.active_task.plan is None:
                fallback = self._attempt_failure_aware_fallback(
                    text, self.active_task, reason="primary planner produced no executable plan"
                )
                if fallback is not None:
                    return fallback
            # Terminal execution failures may also trigger a conservative David hand-off.
            fallback = self._attempt_failure_aware_fallback(
                text, self.active_task, reason="primary execution failed"
            )
            if fallback is not None:
                return fallback
            return response

        if decision.mode == "ask_user" or decision.missing_information:
            missing = decision.missing_information[0] if decision.missing_information else "the missing detail"
            return AdviResponse(f"To proceed, I need to know: {missing}")

        return self._direct_conversation(text, context)

    def _classify_intent(self, text: str, context: AgentContext) -> dict[str, Any]:
        """Compatibility adapter to the unified reasoning engine.

        This method no longer performs a second, legacy LLM classification call.
        External callers that still use the old helper receive a dictionary-shaped
        representation of the authoritative ``ReasoningDecision``.
        """
        decision = self.reasoner.decide(text, context)
        return {
            "intent": decision.intent_hint or decision.mode,
            "reasoning": decision.reason,
            "memory_fact": decision.memory_fact,
            "memory_query": decision.memory_query,
            "task_update": decision.task_update,
            "action": decision.action,
            "goal": decision.goal,
            "confidence": decision.confidence,
            "missing_information": decision.missing_information,
        }

    def _heuristic_classify(self, text: str) -> dict[str, Any]:
        """Fallback intent classifier when LLM is unavailable."""
        lower = text.lower().strip()
        if self.active_task and self.active_task.status == TaskStatus.AWAITING_INPUT:
            return {"intent": "task_input"}
        if self.active_task and self.active_task.status == TaskStatus.AWAITING_CONFIRMATION:
            if lower in {"yes", "yeah", "y", "proceed", "send it", "do it", "confirm", "sure", "ok"}:
                return {"intent": "task_confirm"}
            if lower in {"no", "cancel", "stop", "abort", "nevermind", "don't"}:
                return {"intent": "task_cancel"}
        if self.active_task and any(kw in lower for kw in ["go back", "resume", "continue with", "proceed with the"]):
            return {"intent": "task_resume"}
        if lower.startswith(("remember that", "please remember")):
            return {"intent": "memory_update", "memory_fact": text}
        if any(kw in lower for kw in ["what is my", "tell me my", "who is my", "what's my"]):
            return {"intent": "memory_query", "memory_query": text}
        if any(kw in lower for kw in ["open", "notepad", "chrome", "search", "youtube", "send email", "draft email", "save file", "navigate"]):
            return {"intent": "action_request"}
        return {"intent": "conversation"}

    def _execute_authorized_action(self, action: Action) -> ExecutionResult:
        """Execute one direct action only after the authoritative policy gate.

        Direct cognitive branches (memory operations, etc.) must use the same
        policy boundary as planned actions; the execution engine itself remains
        intentionally policy-agnostic so it can be reused as a low-level executor.
        """
        decision = self.capability_policy.evaluate_action(action)
        if decision.disposition == PolicyDisposition.DENY:
            return ExecutionResult(
                action=action.action,
                success=False,
                error=f"Policy denied action '{action.action}'.",
                human_readable=f"I cannot perform '{action.action}' with the current capabilities.",
                metadata={"policy_denied": True, "policy_reason": decision.reason},
            )
        if decision.disposition == PolicyDisposition.CONFIRM:
            return ExecutionResult(
                action=action.action,
                success=False,
                error="Action requires confirmation before execution.",
                human_readable="This action requires confirmation before execution.",
                metadata={"requires_confirmation": True, "policy_reason": decision.reason},
            )
        return self.execution_engine.execute_action(action)

    def _attempt_failure_aware_fallback(self, text: str, task: ActiveTask | None, *, reason: str) -> AdviResponse | None:
        if not self.fallback_gateway or not self.fallback_gateway.available():
            return None
        raw_class = task.context.get("_last_failure_class") if task else None
        partial = bool(task and any(r.success for r in task.results))
        decision = self.fallback_policy.decide(
            raw_class,
            gateway_available=True,
            partial_results=partial,
            handoff_safe=False,
        )
        if not decision.use_fallback:
            logger.info("David fallback declined: %s", decision.reason)
            return None
        logger.info("Routing to David after primary failure: %s", decision.reason)
        outcome = self.fallback_gateway.process(text, reason=reason or decision.reason)
        if outcome.success:
            return AdviResponse(outcome.text or "I completed the request using the fallback system.")
        logger.warning("David fallback failed: %s", outcome.reason)
        return None

    def _execute_active_task(self) -> AdviResponse:
        """Execute confirmed active task and return grounded response."""
        assert self.active_task is not None
        plan = self.active_task.plan
        goal = self.active_task.goal

        if not plan or not plan.actions:
            self.active_task.mark_completed()
            self.conversation_state.archive_task(self.active_task)
            return AdviResponse(f"Task completed: {goal}.")

        logger.info("Executing confirmed plan for task %r", goal)
        results = self._execute_with_replanning(self.active_task, plan, goal, confirmed_plan=True)
        if self.active_task.status == TaskStatus.AWAITING_CONFIRMATION:
            prompt = str(self.active_task.context.get("confirmation_details") or "Please confirm before I proceed.")
            return AdviResponse(f"{prompt} (Please reply yes or no)")
        return AdviResponse(self._author_grounded_response(goal, results))

    def _plan_and_execute_task(
        self,
        user_goal: str,
        context: AgentContext,
        existing_task: ActiveTask | None = None,
        planning_hints: PlanningHints | None = None,
    ) -> AdviResponse:
        """
        Generate an ActionPlan, enforce permissions, handle missing info / confirmation,
        then execute if ready. May update an existing task or create a new one.
        """
        logger.info("Planning for goal: %r", user_goal)

        plan = self._generate_action_plan(user_goal, context, planning_hints=planning_hints)
        self._turn_plan = plan
        if not plan:
            return AdviResponse("I could not create an executable plan for that request.")

        # Reuse the existing task or create a new one
        task = existing_task or ActiveTask(goal=user_goal)
        task.plan = plan

        # Missing information gate must be checked before the empty-action case.
        if plan.missing_information:
            missing_item = plan.missing_information[0]
            task.set_awaiting_input(missing_item)
            self.active_task = task
            return AdviResponse(f"To proceed, I need to know: {missing_item}")

        if not plan.actions:
            reason = (plan.reason or "").lower()
            if "unavailable actions" in reason or "no executable" in reason:
                return AdviResponse("I cannot perform that request with the capabilities currently available.")
            return AdviResponse("I could not turn that request into an executable action with the capabilities currently available.")

        # Capability policy gate — authoritative system policy; the LLM cannot bypass it.
        denial = self.capability_policy.first_denial(plan.actions)
        if denial is not None:
            logger.warning("Policy denied action '%s': %s", denial.action, denial.reason)
            return AdviResponse(f"I cannot perform '{denial.action}' with the current capabilities.")

        policy_confirm = self.capability_policy.confirmation_actions(plan.actions)
        needs_confirm = plan.confirmation_required or bool(policy_confirm)
        if needs_confirm:
            confirm_prompt = plan.confirmation_prompt
            if not confirm_prompt:
                action_names = ", ".join(a.action for a in policy_confirm)
                if action_names:
                    confirm_prompt = (
                        f"This will perform: {action_names}. "
                        f"Please confirm before I proceed."
                    )
                else:
                    confirm_prompt = "Please confirm before I proceed with this action."
            confirmation = self.confirmation_manager.issue(plan)
            task.set_awaiting_confirmation(
                confirm_prompt,
                confirmation.fingerprint,
                confirmation.issued_at,
                confirmation.expires_at,
            )
            self.active_task = task
            return AdviResponse(f"{confirm_prompt} (Please reply yes or no)")

        # Execute immediately
        self.active_task = task
        results = self._execute_with_replanning(task, plan, user_goal)
        if task.status == TaskStatus.AWAITING_CONFIRMATION:
            prompt = str(task.context.get("confirmation_details") or "Please confirm before I proceed.")
            return AdviResponse(f"{prompt} (Please reply yes or no)")
        return AdviResponse(self._author_grounded_response(user_goal, results))

    def _execute_with_replanning(
        self,
        task: ActiveTask,
        plan: ActionPlan,
        goal: str,
        confirmed_plan: bool = False,
    ) -> list[ExecutionResult]:
        """Execute, then make bounded recovery decisions when a plan fails."""
        all_results: list[ExecutionResult] = []
        current_plan = plan
        replan_count = int(task.context.get("_replan_count", 0))
        confirmation_already_granted = confirmed_plan

        while True:
            # Every newly proposed recovery plan gets its own policy evaluation.
            # A prior approval never carries forward to a different plan.
            decisions = self.capability_policy.evaluate_plan(current_plan.actions)
            denial = next((d for d in decisions if d.disposition == PolicyDisposition.DENY), None)
            if denial is not None:
                task.mark_failed(f"Policy denied recovery action '{denial.action}'.")
                self.conversation_state.archive_task(task)
                return all_results

            recovery_confirmation = [
                action for action, decision in zip(current_plan.actions, decisions)
                if decision.disposition == PolicyDisposition.CONFIRM
            ]
            if recovery_confirmation and not confirmation_already_granted:
                confirmation = self.confirmation_manager.issue(current_plan)
                prompt = (
                    "Recovery requires your confirmation before I continue: "
                    + ", ".join(action.action for action in recovery_confirmation)
                    + "."
                )
                task.plan = current_plan
                task.set_awaiting_confirmation(
                    prompt,
                    confirmation.fingerprint,
                    confirmation.issued_at,
                    confirmation.expires_at,
                )
                task.context["_replan_count"] = replan_count
                return all_results

            # A consumed confirmation applies only to this exact original plan.
            # Any subsequent replan must pass through policy and, if needed, ask again.
            confirmation_already_granted = False

            try:
                results = self.execution_engine.execute_plan(current_plan, task_id=task.task_id)
            except TypeError as exc:
                # Preserve compatibility with injected/legacy test doubles and executors.
                if "task_id" not in str(exc):
                    raise
                results = self.execution_engine.execute_plan(current_plan)
            all_results.extend(results)
            self._turn_results.extend(results)
            self._accumulate_results(results)
            task.results.extend(results)

            failed_index = next((i for i, r in enumerate(results) if not r.success), None)
            goal_evidence = self.goal_verifier.verify(current_plan, results)
            task.context["goal_verification"] = {
                "status": goal_evidence.status,
                "reason": goal_evidence.reason,
                "evidence": goal_evidence.evidence,
            }

            if failed_index is None and goal_evidence.status == GoalVerificationStatus.VERIFIED:
                task.mark_completed()
                self.conversation_state.archive_task(task)
                return all_results

            # A definitive execution/verification failure, or a purely uncertain
            # goal outcome, becomes the next bounded recovery signal.
            if failed_index is not None:
                failed_result = results[failed_index]
                failed_action = current_plan.actions[min(failed_index, len(current_plan.actions) - 1)]
                trigger = (
                    "verification_failed"
                    if failed_result.verification_status == VerificationStatus.FAILED
                    else "execution_failure"
                )
            else:
                meaningful = [r for r in results if r.action != "finish"]
                failed_result = meaningful[-1] if meaningful else ExecutionResult(
                    action="goal_verification", success=True,
                    error=goal_evidence.reason,
                    verification_status=VerificationStatus.UNCERTAIN,
                )
                failed_action = current_plan.actions[-1] if current_plan.actions else Action(action="finish")
                trigger = "verification_uncertain"

            max_replans = max(0, int(getattr(self.replanner, "max_replans", 2)))
            if replan_count >= max_replans:
                if goal_evidence.status == GoalVerificationStatus.UNCERTAIN and failed_index is None:
                    task.mark_completed()
                else:
                    task.mark_failed(failed_result.error or "Bounded recovery exhausted.")
                task.context["_last_failure_class"] = failed_result.metadata.get("failure_class", FailureClass.UNKNOWN.value)
                self.conversation_state.archive_task(task)
                return all_results

            decision = self.replanner.decide(
                goal=goal,
                plan=current_plan,
                results=all_results,
                failed_action=failed_action,
                available_actions=[
                    action
                    for capability in self.registry.list_available()
                    for action in capability.supported_actions
                ],
                replan_count=replan_count,
                trigger=trigger,
                goal_verification={
                    "status": goal_evidence.status,
                    "reason": goal_evidence.reason,
                    "evidence": goal_evidence.evidence,
                },
            )

            if decision.decision != "replan" or decision.action is None:
                if decision.await_user:
                    task.set_awaiting_input(decision.reason or "additional information")
                elif goal_evidence.status == GoalVerificationStatus.UNCERTAIN and failed_index is None:
                    # No definitive failure exists, so preserve the task as completed-with-uncertainty.
                    task.mark_completed()
                else:
                    task.mark_failed(failed_result.error or decision.reason or "Unknown failure")
                task.context["_last_failure_class"] = failed_result.metadata.get("failure_class", FailureClass.UNKNOWN.value)
                self.conversation_state.archive_task(task)
                return all_results

            # CapabilityRegistry is the authority on whether the proposed action exists.
            if not self.registry.get_capability_for_action(decision.action.action):
                logger.warning("Replanner proposed unavailable action: %s", decision.action.action)
                task.mark_failed(f"Recovery action '{decision.action.action}' is unavailable.")
                task.context["_last_failure_class"] = FailureClass.UNAVAILABLE_CAPABILITY.value
                self.conversation_state.archive_task(task)
                return all_results

            replan_count += 1
            task.context["_replan_count"] = replan_count
            logger.info("Applying bounded recovery action %r (attempt %d)", decision.action.action, replan_count)
            current_plan = ActionPlan(
                goal=goal,
                actions=[decision.action],
                reason=decision.reason,
            )

    def _generate_action_plan(
        self,
        goal: str,
        context: AgentContext,
        planning_hints: PlanningHints | None = None,
    ) -> ActionPlan:
        """Delegate goal-to-action planning to the dedicated PlannerEngine."""
        return self.planner.plan(goal, context, hints=planning_hints)


    def _recent_research_context(self, limit: int = 3) -> list[dict[str, Any]]:
        """Expose bounded prior research so follow-up turns can resolve source questions."""
        items: list[dict[str, Any]] = []
        if self.research_evidence_store is not None:
            try:
                for item in self.research_evidence_store.latest(limit):
                    items.append({
                        "research_id": item.research_id,
                        "question": item.question,
                        "answer": item.answer,
                        "sources": [
                            {"index": s.get("index"), "title": s.get("title"), "url": s.get("url"), "domain": s.get("domain")}
                            for s in item.sources
                        ],
                        "source_claims": item.source_claims,
                        "uncertainty": item.uncertainty,
                        "conflicts": [c.__dict__ for c in item.conflicts],
                    })
            except Exception as exc:
                logger.warning("Research context retrieval failed: %s", exc)
        return items

    def _answer_research_followup(self, text: str, query: str | None = None) -> AdviResponse:
        stores = self.research_evidence_store.latest(3) if self.research_evidence_store is not None else []
        if not stores:
            return AdviResponse("I do not have stored research evidence for that question.")
        q = (query or text).lower()
        selected = next((r for r in stores if any(term in r.question.lower() for term in q.split() if len(term) >= 4)), stores[0])
        if "conflict" in q or "disagree" in q or "different" in q:
            if selected.conflicts:
                lines = [f"Sources {', '.join(map(str, c.source_indices))} differ on {c.topic}: {c.excerpts[0]} / {c.excerpts[1]}" for c in selected.conflicts[:3]]
                return AdviResponse("Here are the conflicts I recorded: " + " ".join(lines))
            return AdviResponse("I did not record a definite source conflict in the collected evidence.")
        lines = []
        for claim in selected.source_claims[:8]:
            idx = claim.get("source_index")
            source = next((s for s in selected.sources if s.get("index") == idx), None)
            if source:
                lines.append(f"[S{idx}] {claim.get('claim')} — {source.get('title') or source.get('url')} ({source.get('url')})")
        if "source" in q or "where" in q or "cite" in q or "said" in q:
            if lines:
                return AdviResponse("I traced the research claims to these sources: " + " ".join(lines))
        source_lines = [f"[S{s.get('index')}] {s.get('title')} — {s.get('url')}" for s in selected.sources[:5]]
        return AdviResponse("The latest stored research was based on: " + " ".join(source_lines))

    def _author_grounded_response(self, goal: str, results: list[ExecutionResult]) -> str:
        """
        Formulate a natural language response grounded in execution outcomes.

        Distinguishes:
          verified success   → confident confirmation
          unverified success → hedged but positive (not treated as failure)
          execution failure  → honest failure report
        """
        if not results:
            return f"No actions were executed for: {goal}."

        non_finish = [r for r in results if r.action != "finish"]
        failed = [r for r in non_finish if not r.success or r.verification_status == VerificationStatus.FAILED]

        if failed:
            f = failed[0]
            return (
                f"I attempted to {goal}, but ran into an issue during '{f.action}': {f.error}."
            )

        research = next((r for r in non_finish if r.action == "research_web_multi" and r.success), None)
        if research is not None:
            synthesis = self.research_synthesizer.synthesize(goal, research.metadata)
            if self.research_evidence_store is not None:
                try:
                    research_id = str(research.metadata.get("research_id") or f"research-{int(research.executed_at * 1000)}")
                    self.research_evidence_store.save(
                        research_id=research_id,
                        question=goal,
                        evidence=research.metadata,
                        answer=synthesis.answer,
                        source_claims=synthesis.source_claims,
                        uncertainty=synthesis.uncertainty,
                    )
                except Exception as exc:
                    logger.warning("Could not persist research evidence: %s", exc)
            return synthesis.answer

        summary_items = [r.human_readable for r in non_finish if r.human_readable]
        uncertain = [r for r in non_finish if r.verification_status == VerificationStatus.UNCERTAIN]

        if summary_items:
            details = " ".join(summary_items)
            if uncertain:
                return (
                    f"I completed the requested actions, but I could not fully verify the final state. "
                    f"{details} "
                    f"({len(uncertain)} step(s) remain uncertain.)"
                )
            return f"Done and verified. {details}"

        return f"I have completed your request: {goal}."

    def _accumulate_results(self, results: list[ExecutionResult]) -> None:
        """Maintain a bounded ring of recent results for cross-turn context."""
        self.conversation_state.add_results(results)
        self._persist_current_task()

    def _mark_interrupted_task(self, task: ActiveTask) -> None:
        """Detect a journaled in-flight step and require safe recovery before resume."""
        if self.execution_journal is None or not task.plan:
            return
        fingerprint = ExecutionJournal.fingerprint_plan(task.plan.goal, task.plan.actions)
        try:
            interrupted = self.execution_journal.interrupted_step(task.task_id, fingerprint)
        except Exception as exc:
            logger.warning("Could not inspect execution journal for %s: %s", task.task_id, exc)
            interrupted = None
        if not interrupted:
            return
        task.context["_interrupted_step"] = {
            "step_index": interrupted["step_index"],
            "action": interrupted["action"],
            "action_fingerprint": interrupted["action_fingerprint"],
            "started_at": interrupted["started_at"],
            "recovery_required": True,
        }
        # Do not blindly repeat a possibly side-effecting action after a crash.
        task.status = TaskStatus.AWAITING_INPUT
        task.waiting_for = "interrupted_execution_review"

    def _persist_current_task(self) -> None:
        task = self.active_task
        if task is None or self.task_persistence is None:
            return
        try:
            self.task_persistence.save(task)
        except Exception as exc:
            logger.warning("Task persistence failed for %s: %s", task.task_id, exc)

    def _answer_memory_query(self, query: str, facts: list[str], context: AgentContext) -> AdviResponse:
        """Answer a personal memory query. The active task is preserved and untouched."""
        facts_text = "\n".join(f"- {f}" for f in facts) if facts else "No specific memory record found."
        task_note = (
            f"\n\n(Note: current work remains available: {self.active_task.goal!r}. "
            "The memory answer does not discard it.)"
            if self.active_task
            else ""
        )
        prompt = f"""{context.identity_prompt}

The user asked: "{query}"

Retrieved evidence from memory:
{facts_text}{task_note}

Provide a concise, helpful, truthful answer based on this evidence. Do not fabricate missing information."""
        try:
            resp = self.provider.generate(prompt)
            return AdviResponse((resp.text if hasattr(resp, "text") else str(resp)).strip())
        except Exception:
            if facts:
                return AdviResponse(f"According to your records: {facts[0]}")
            return AdviResponse(f"I don't have a record of that in my memory yet.")

    def _direct_conversation(self, text: str, context: AgentContext) -> AdviResponse:
        """Handle pure conversational turns."""
        task_note = (
            f"\n\n(Current work remains available: {self.active_task.goal!r})"
            if self.active_task
            else ""
        )
        prompt = f"""{context.identity_prompt}{task_note}

{context.format_prompt_context()}

User: {text}
ADVI:"""
        try:
            resp = self.provider.generate(prompt)
            reply = resp.text if hasattr(resp, "text") else str(resp)
            return AdviResponse(reply.strip())
        except Exception as exc:
            logger.exception("Direct conversation generation failed: %s", exc)
            return AdviResponse("I'm sorry, I encountered a brief issue processing that.")

    def _record_turn(self, user_msg: str, assistant_msg: str) -> None:
        """Save turn to short-term memory and session buffer."""
        self.short_term_memory.add("user", user_msg)
        self.short_term_memory.add("assistant", assistant_msg)
        self.session_buffer.add([
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": assistant_msg},
        ])
        self.conversation_state.record_turn()

    @staticmethod
    def _extract_json(raw: str) -> str:
        """Strip markdown code fences and extract JSON object."""
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
        if match:
            return match.group(1).strip()
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            return raw[start : end + 1]
        return raw.strip()
