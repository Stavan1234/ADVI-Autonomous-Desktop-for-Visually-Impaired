from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class FallbackOutcome:
    success: bool
    text: str = ""
    results: list[Any] | None = None
    reason: str = ""


class FallbackGateway(Protocol):
    """Narrow boundary between ADVI's brain and the independent David pipeline."""

    def available(self) -> bool: ...

    def process(self, user_input: str, *, reason: str = "") -> FallbackOutcome: ...


class DavidFallbackGateway:
    """Adapter exposing the existing David fallback service through ADVI's narrow gateway."""

    def __init__(self, service: Any) -> None:
        self.service = service

    def available(self) -> bool:
        return self.service is not None

    def process(self, user_input: str, *, reason: str = "") -> FallbackOutcome:
        try:
            result = self.service.process(user_input)
        except Exception as exc:
            return FallbackOutcome(success=False, reason=f"David fallback failed: {exc}")

        text = str(getattr(result, "text", "") or "")
        if not text:
            results = getattr(result, "results", None) or []
            successful = [r for r in results if getattr(r, "success", False)]
            if successful:
                text = "David completed the fallback task."
        return FallbackOutcome(
            success=bool(getattr(result, "success", False)),
            text=text,
            results=list(getattr(result, "results", None) or []),
            reason=reason or ("fallback execution failed" if not getattr(result, "success", False) else ""),
        )
