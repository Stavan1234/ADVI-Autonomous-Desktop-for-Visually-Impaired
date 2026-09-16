from __future__ import annotations

import logging
import time
from datetime import datetime, timezone


from ..core.pipeline_trace import (
    llm_response_to_dict,
    next_llm_call_id,
    trace,
    trace_exception,
)
from .base import LLMProvider, LLMResponse
from .errors import (
    LLMAuthenticationError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
)


logger = logging.getLogger(__name__)


class GroqProvider(LLMProvider):
    """Groq-backed LLM provider."""

    def __init__(
        self,
        api_key: str,
        model: str,
    ) -> None:
        try:
            from groq import Groq
        except ImportError as exc:
            raise LLMUnavailableError(
                "Groq SDK is not installed."
            ) from exc

        self._client = Groq(
            api_key=api_key,
            timeout=30.0,
            max_retries=0,
        )
        self._model = model

    def close(self) -> None:
        client = getattr(self, "_client", None)
        closer = getattr(client, "close", None)
        if callable(closer):
            closer()

    @property
    def name(self) -> str:
        return "groq"

    @property
    def model(self) -> str:
        return self._model

    def chat(
        self,
        messages: list[dict[str, str]],
    ) -> LLMResponse:
        started = time.perf_counter()
        llm_id = next_llm_call_id()
        request_started = datetime.now(timezone.utc).isoformat()

        system_prompt = None
        for message in messages:
            if message.get("role") == "system":
                system_prompt = message.get("content")
                break

        trace(
            "groq.request",
            provider=self.name,
            model=self._model,
            purpose="final_response",
            llm_call_id=llm_id,
            request_started_at=request_started,
            messages=messages,
            system_prompt=system_prompt,
            structured_output=False,
        )

        from groq import (
            APIConnectionError,
            APITimeoutError,
            AuthenticationError,
            RateLimitError,
        )

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
            )

        except AuthenticationError as exc:
            trace_exception(
                "groq.error",
                exc,
                provider=self.name,
                model=self._model,
                llm_call_id=llm_id,
            )
            raise LLMAuthenticationError(
                "Groq authentication failed."
            ) from exc

        except RateLimitError as exc:
            trace_exception(
                "groq.error",
                exc,
                provider=self.name,
                model=self._model,
                llm_call_id=llm_id,
            )
            raise LLMRateLimitError(
                "Groq rate limit or quota was exceeded."
            ) from exc

        except APITimeoutError as exc:
            trace_exception(
                "groq.error",
                exc,
                provider=self.name,
                model=self._model,
                llm_call_id=llm_id,
            )
            raise LLMTimeoutError(
                "Groq request timed out."
            ) from exc

        except APIConnectionError as exc:
            trace_exception(
                "groq.error",
                exc,
                provider=self.name,
                model=self._model,
                llm_call_id=llm_id,
            )
            raise LLMUnavailableError(
                "Could not connect to Groq."
            ) from exc

        latency_ms = (
            time.perf_counter() - started
        ) * 1000

        if not response.choices:
            trace(
                "groq.response.raw",
                provider=self.name,
                model=self._model,
                llm_call_id=llm_id,
                status="error",
                latency_ms=round(latency_ms, 2),
                error="no_choices",
                raw_response_id=getattr(response, "id", None),
            )
            raise LLMUnavailableError(
                "Groq returned no choices."
            )

        message = response.choices[0].message
        text = message.content or ""

        usage = response.usage
        finish_reason = response.choices[0].finish_reason

        trace(
            "groq.response.raw",
            provider=self.name,
            model=self._model,
            llm_call_id=llm_id,
            status="success",
            latency_ms=round(latency_ms, 2),
            raw_text=text,
            raw_text_empty=not bool(text.strip()),
            finish_reason=finish_reason,
            request_id=getattr(response, "id", None),
            usage={
                "prompt_tokens": (
                    usage.prompt_tokens
                    if usage is not None
                    else None
                ),
                "completion_tokens": (
                    usage.completion_tokens
                    if usage is not None
                    else None
                ),
                "total_tokens": (
                    usage.total_tokens
                    if usage is not None
                    else None
                ),
            },
            response_type=type(response).__name__,
        )

        if not text.strip():
            raise LLMUnavailableError(
                "Groq returned an empty response."
            )

        llm_response = LLMResponse(
            text=text,
            provider=self.name,
            model=self.model,
            input_tokens=(
                usage.prompt_tokens
                if usage is not None
                else None
            ),
            output_tokens=(
                usage.completion_tokens
                if usage is not None
                else None
            ),
            latency_ms=latency_ms,
            finish_reason=finish_reason,
            request_id=getattr(
                response,
                "id",
                None,
            ),
        )

        trace(
            "groq.response.normalized",
            provider=self.name,
            model=self.model,
            llm_call_id=llm_id,
            normalized=llm_response_to_dict(llm_response),
        )

        return llm_response