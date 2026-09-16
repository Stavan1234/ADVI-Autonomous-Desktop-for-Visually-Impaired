from __future__ import annotations

from dataclasses import dataclass

from .intent_schema import Intent


@dataclass(frozen=True)
class RouteResult:
    fallback: bool
    reason: str


class FallbackRouter:
    """
    Decide whether an agentic desktop intent should use
    the fallback execution system.

    This router does not execute actions and does not
    modify the built-in ADVI execution flow.
    """

    # Goals handled by the agentic desktop fallback.
    FALLBACK_GOALS = {
        "open_application",
        "send_email",
        "search_web",
        "play_music",
        "create_document",
        "shutdown_system",
    }

    def route(
        self,
        intent: Intent,
    ) -> RouteResult:
        goal = intent.goal.strip().lower()

        if not goal:
            return RouteResult(
                fallback=False,
                reason="missing_goal",
            )

        if goal == "unsupported_request":
            return RouteResult(
                fallback=False,
                reason="unsupported_request",
            )

        if goal in self.FALLBACK_GOALS:
            return RouteResult(
                fallback=True,
                reason="fallback_goal",
            )

        return RouteResult(
            fallback=False,
            reason="unknown_goal",
        )