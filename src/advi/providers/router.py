from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable, Sequence

from .base import LLMProvider, LLMResponse
from .errors import (
    LLMAuthenticationError,
    LLMError,
    LLMRateLimitError,
    LLMResponseError,
    LLMTimeoutError,
    LLMUnavailableError,
)

logger = logging.getLogger(__name__)


RETRYABLE_LLM_ERRORS = (
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
    LLMResponseError,
    LLMAuthenticationError,
)


@dataclass(frozen=True)
class ProviderAttempt:
    provider: str
    success: bool
    error_type: str | None = None
    error: str | None = None


class ResilientLLMProvider(LLMProvider):
    """Route each LLM request through an ordered provider chain.

    Providers are attempted at most once per request. A fallback provider is
    used only after a normalized LLMError; arbitrary programming exceptions are
    deliberately re-raised so implementation bugs are not hidden as outages.
    """

    def __init__(
        self,
        providers: Sequence[LLMProvider],
        *,
        on_failure: Callable[[ProviderAttempt], None] | None = None,
    ) -> None:
        self._providers = tuple(p for p in providers if p is not None)
        if not self._providers:
            raise ValueError("At least one LLM provider is required.")
        self._on_failure = on_failure
        self.last_attempts: tuple[ProviderAttempt, ...] = ()

    def close(self) -> None:
        for provider in reversed(self._providers):
            try:
                provider.close()
            except Exception:
                logger.exception("Failed to close LLM provider %s", provider.name)

    @property
    def name(self) -> str:
        return "+".join(provider.name for provider in self._providers)

    @property
    def model(self) -> str:
        return self._providers[0].model

    @property
    def providers(self) -> tuple[LLMProvider, ...]:
        return self._providers

    def chat(self, messages: list[dict[str, str]]) -> LLMResponse:
        return self._route(lambda provider: provider.chat(messages))

    def structured(
        self,
        messages: list[dict[str, str]],
        schema: dict,
    ) -> LLMResponse:
        return self._route(lambda provider: provider.structured(messages, schema))

    def _route(self, call: Callable[[LLMProvider], LLMResponse]) -> LLMResponse:
        attempts: list[ProviderAttempt] = []
        last_error: LLMError | None = None

        for index, provider in enumerate(self._providers):
            started = time.perf_counter()
            try:
                response = call(provider)
                if not isinstance(response, LLMResponse):
                    raise LLMResponseError(
                        f"Provider {provider.name} returned an invalid response object."
                    )
                if not response.text or not response.text.strip():
                    raise LLMResponseError(
                        f"Provider {provider.name} returned an empty response."
                    )
                attempts.append(ProviderAttempt(provider=provider.name, success=True))
                self.last_attempts = tuple(attempts)
                if index:
                    logger.warning(
                        "LLM provider recovery succeeded with %s after fallback from %s.",
                        provider.name,
                        attempts[-2].provider,
                    )
                return response
            except LLMError as exc:
                last_error = exc
                attempt = ProviderAttempt(
                    provider=provider.name,
                    success=False,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                attempts.append(attempt)
                self._notify_failure(attempt)
                logger.warning(
                    "LLM provider %s failed after %.1fms: %s",
                    provider.name,
                    (time.perf_counter() - started) * 1000,
                    exc,
                )
                if index == len(self._providers) - 1:
                    break
                continue
            except Exception:
                # Unexpected code defects should not silently switch providers.
                self.last_attempts = tuple(attempts)
                raise

        self.last_attempts = tuple(attempts)
        if last_error is not None:
            raise last_error
        raise LLMUnavailableError("No LLM provider was available.")

    def _notify_failure(self, attempt: ProviderAttempt) -> None:
        if self._on_failure is not None:
            try:
                self._on_failure(attempt)
            except Exception:
                logger.exception("LLM failure observer raised an exception.")
