from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentContext:
    """
    Explicit, coherent context representation assembled for the ADVI Brain.
    Selects only the relevant subset needed for reasoning without unbounded token dumping.
    """
    current_message: str
    recent_history: list[dict[str, str]] = field(default_factory=list)
    relevant_memories: list[str] = field(default_factory=list)
    active_task: dict[str, Any] | None = None
    recent_tasks: list[dict[str, Any]] = field(default_factory=list)
    recent_research: list[dict[str, Any]] = field(default_factory=list)
    previous_action_results: list[dict[str, Any]] = field(default_factory=list)
    available_capabilities: str = ""
    identity_prompt: str = ""
    pending_confirmation: bool = False
    resolved_references: list[dict[str, Any]] = field(default_factory=list)
    system_metadata: dict[str, Any] = field(default_factory=dict)

    def format_prompt_context(self) -> str:
        """Format selected context into a structured block for the LLM."""
        sections = []

        if self.relevant_memories:
            mem_text = "\n".join(f"- {m}" for m in self.relevant_memories)
            sections.append(f"### Known User Facts (from Memory):\n{mem_text}")

        if self.active_task:
            task_info = (
                f"- Goal: {self.active_task.get('goal')}\n"
                f"- Status: {self.active_task.get('status')}\n"
                f"- Details: {self.active_task.get('context')}"
            )
            sections.append(f"### Active Task Context:\n{task_info}")

        if self.recent_tasks:
            task_text = "\n".join(
                f"- {t.get('goal')} [{t.get('status')}] (task_id={t.get('task_id')})"
                for t in self.recent_tasks[-3:]
            )
            sections.append(f"### Recent Work:\n{task_text}")

        if self.recent_research:
            research_text = "\n".join(
                f"- {r.get('question')} (research_id={r.get('research_id')}) sources={len(r.get('sources') or [])}"
                for r in self.recent_research[-3:]
            )
            sections.append(f"### Recent Research Evidence:\n{research_text}")

        if self.previous_action_results:
            results_text = "\n".join(
                f"- Action {r.get('action')}: {'Success' if r.get('success') else 'Failed'} - {r.get('human_readable') or r.get('error')}"
                for r in self.previous_action_results[-5:]
            )
            sections.append(f"### Recent Execution Results:\n{results_text}")

        if self.resolved_references:
            refs="\n".join(f"- {r.get('kind')}: {r.get('label') or r.get('value')}" for r in self.resolved_references[-4:])
            sections.append(f"### Resolved Conversation References:\n{refs}")

        if self.available_capabilities:
            sections.append(f"### Available Capabilities:\n{self.available_capabilities}")

        return "\n\n".join(sections)
