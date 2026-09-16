from __future__ import annotations

import os
import textwrap
from typing import Any, Iterable


class TerminalTraceRenderer:
    """Compact, human-readable per-turn pipeline display.

    This intentionally exposes routing and execution summaries, not hidden model
    chain-of-thought or raw prompts/responses. Detailed diagnostics remain in
    ``logs/advi.log``.
    """

    def __init__(self, *, enabled: bool | None = None) -> None:
        if enabled is None:
            enabled = os.getenv("ADVI_TERMINAL_TRACE", "1").strip().lower() not in {
                "0", "false", "off", "no"
            }
        self.enabled = enabled
        self.width = 74

    def render(
        self,
        *,
        user_input: str,
        decision: Any | None = None,
        plan: Any | None = None,
        results: Iterable[Any] | None = None,
        response: str = "",
        task_status: str | None = None,
    ) -> None:
        if not self.enabled:
            return

        lines: list[str] = []
        self._add(lines, "Input", user_input)

        if decision is not None:
            mode = getattr(decision, "mode", "conversation")
            confidence = getattr(decision, "confidence", None)
            action = getattr(decision, "action", None)
            route = mode
            if action:
                route += f" → {action}"
            if confidence is not None:
                route += f" ({float(confidence):.2f})"
            self._add(lines, "Route", route)

        if plan is not None:
            actions = getattr(plan, "actions", None) or []
            if actions:
                lines.append("Plan")
                for index, action in enumerate(actions, start=1):
                    name = getattr(action, "action", "unknown")
                    params = getattr(action, "parameters", {}) or {}
                    param_text = self._compact_mapping(params)
                    suffix = f" — {param_text}" if param_text else ""
                    lines.append(f"  {index}. {name}{suffix}")
            else:
                self._add(lines, "Plan", "No executable steps")

        result_list = list(results or [])
        if result_list:
            lines.append("Execution")
            for result in result_list[-6:]:
                action = getattr(result, "action", "unknown")
                success = bool(getattr(result, "success", False))
                verified = getattr(result, "verification_status", None)
                if hasattr(verified, "value"):
                    verified = verified.value
                marker = "✓" if success else "✗"
                status = f", {verified}" if verified else ""
                lines.append(f"  {marker} {action}{status}")

        if task_status:
            self._add(lines, "Task", task_status)
        self._add(lines, "ADVI", response)

        print()
        print("╭" + "─" * (self.width - 2) + "╮")
        for line in lines:
            for wrapped in textwrap.wrap(
                line,
                width=self.width - 4,
                replace_whitespace=False,
                drop_whitespace=True,
            ) or [""]:
                print("│ " + wrapped.ljust(self.width - 4) + " │")
        print("╰" + "─" * (self.width - 2) + "╯")

    def _add(self, lines: list[str], label: str, value: Any) -> None:
        text = str(value).strip()
        if not text:
            return
        lines.append(f"{label:<9} {text}")

    @staticmethod
    def _compact_mapping(mapping: dict[str, Any]) -> str:
        parts: list[str] = []
        for key, value in mapping.items():
            text = repr(value)
            if len(text) > 90:
                text = text[:87] + "..."
            parts.append(f"{key}={text}")
        return ", ".join(parts)
