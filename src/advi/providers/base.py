from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMResponse:
    """Normalized response returned by every LLM provider."""

    text: str
    provider: str
    model: str

    input_tokens: int | None = None
    output_tokens: int | None = None

    latency_ms: float | None = None
    finish_reason: str | None = None

    request_id: str | None = None

    rate_limit_requests_remaining: int | None = None
    rate_limit_requests_reset: str | None = None

    rate_limit_tokens_remaining: int | None = None
    rate_limit_tokens_reset: str | None = None


class LLMProvider(ABC):
    """Common interface for all ADVI language-model providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider identifier."""

    @property
    @abstractmethod
    def model(self) -> str:
        """Active model identifier."""

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, str]],
    ) -> LLMResponse:
        """Send a conversation and return a normalized response."""

    def close(self) -> None:
        """Release provider resources. Providers may override this."""
        return None

    def structured(
        self,
        messages: list[dict[str, str]],
        schema: dict,
    ) -> LLMResponse:
        """
        Send a structured-output request.

        Providers with native structured-output support should
        override this method. The default falls back to normal
        chat so lightweight test doubles and providers that do not
        yet support native schemas remain compatible.
        """
        return self.chat(messages)

    def generate(
        self,
        prompt: str,
    ) -> LLMResponse:
        """Send a single prompt string and return a normalized response."""
        return self.chat([{"role": "user", "content": prompt}])
