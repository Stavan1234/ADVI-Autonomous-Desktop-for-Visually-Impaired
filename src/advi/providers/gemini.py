# from _pytest.assertion import compare_text
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
from .gemini_trace import (
    gemini_config_to_trace_dict,
    gemini_contents_to_trace_list,
    gemini_response_to_trace_dict,
)


logger = logging.getLogger(__name__)


class GeminiProvider(LLMProvider):
    """Gemini-backed LLM provider."""

    def __init__(
        self,
        api_key: str,
        model: str,
    ) -> None:
        try:
            from google import genai
        except ImportError as exc:
            raise LLMUnavailableError(
                "Google GenAI SDK is not installed."
            ) from exc

        self._client = genai.Client(
            api_key=api_key,
        )
        self._model = model

    def close(self) -> None:
        client = getattr(self, "_client", None)
        closer = getattr(client, "close", None)
        if callable(closer):
            closer()

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def model(self) -> str:
        return self._model

    def chat(
        self,
        messages: list[dict[str, str]],
    ) -> LLMResponse:
        """Send a normal conversational request to Gemini."""

        from google.genai import types

        started = time.perf_counter()

        contents: list[types.Content] = []
        system_instruction: str | None = None

        for message in messages:
            role = message.get(
                "role",
                "user",
            ).strip()

            content = message.get(
                "content",
                "",
            ).strip()

            if not content:
                continue

            if role == "system":
                if system_instruction:
                    system_instruction += (
                        "\n\n" + content
                    )
                else:
                    system_instruction = content

                continue

            gemini_role = (
                "model"
                if role == "assistant"
                else "user"
            )

            contents.append(
                types.Content(
                    role=gemini_role,
                    parts=[
                        types.Part.from_text(
                            text=content,
                        ),
                    ],
                )
            )

        if not contents:
            raise LLMUnavailableError(
                "Gemini received no usable conversation content."
            )

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            max_output_tokens=1024,
        )

        llm_id = next_llm_call_id()
        request_started = datetime.now(timezone.utc).isoformat()

        trace(
            "gemini.chat.request",
            provider=self.name,
            model=self._model,
            purpose="chat",
            llm_call_id=llm_id,
            request_started_at=request_started,
            contents_count=len(contents),
            contents=gemini_contents_to_trace_list(contents),
            system_instruction=system_instruction,
            config=gemini_config_to_trace_dict(config),
            structured_output=False,
        )

        try:
            response = (
                self._client.models.generate_content(
                    model=self._model,
                    contents=contents,
                    config=config,
                )
            )

        except Exception as exc:
            message = str(exc).lower()

            trace_exception(
                "gemini.chat.error",
                exc,
                provider=self.name,
                model=self._model,
                llm_call_id=llm_id,
            )

            if (
                "401" in message
                or "403" in message
                or "api key" in message
                or "authentication" in message
            ):
                raise LLMAuthenticationError(
                    "Gemini authentication failed."
                ) from exc

            if (
                "429" in message
                or "quota" in message
                or "rate limit" in message
            ):
                raise LLMRateLimitError(
                    "Gemini rate limit or quota was exceeded."
                ) from exc

            if (
                "timeout" in message
                or "deadline" in message
            ):
                raise LLMTimeoutError(
                    "Gemini request timed out."
                ) from exc

            raise LLMUnavailableError(
                "Gemini request failed."
            ) from exc

        latency_ms = (
            time.perf_counter() - started
        ) * 1000

        trace(
            "gemini.chat.response.raw",
            provider=self.name,
            model=self._model,
            llm_call_id=llm_id,
            status="success",
            latency_ms=round(latency_ms, 2),
            raw_response=gemini_response_to_trace_dict(response),
            http_requests=1,
        )

        text = response.text or ""

        if not text.strip():
            raise LLMUnavailableError(
                "Gemini returned an empty response."
            )

        usage = response.usage_metadata

        llm_response = LLMResponse(
            text=text,
            provider=self.name,
            model=self.model,
            input_tokens=(
                getattr(
                    usage,
                    "prompt_token_count",
                    None,
                )
                if usage is not None
                else None
            ),
            output_tokens=(
                getattr(
                    usage,
                    "candidates_token_count",
                    None,
                )
                if usage is not None
                else None
            ),
            latency_ms=latency_ms,
            finish_reason=None,
            request_id=getattr(
                response,
                "response_id",
                None,
            ),
        )

        trace(
            "gemini.chat.response.normalized",
            provider=self.name,
            model=self.model,
            llm_call_id=llm_id,
            raw_response=gemini_response_to_trace_dict(response),
            normalized=llm_response_to_dict(llm_response),
        )

        return llm_response

    def structured(
        self,
        messages: list[dict[str, str]],
        schema: dict,
    ) -> LLMResponse:
        """
        Generate schema-constrained JSON using Gemini.

        This is intentionally separate from chat(). Structured
        requests use Gemini's native JSON response configuration.
        """

        from google.genai import types

        started = time.perf_counter()

        contents: list[types.Content] = []
        system_instruction: str | None = None

        for message in messages:
            role = message.get(
                "role",
                "user",
            ).strip()

            content = message.get(
                "content",
                "",
            ).strip()

            if not content:
                continue

            if role == "system":
                if system_instruction:
                    system_instruction += (
                        "\n\n" + content
                    )
                else:
                    system_instruction = content

                continue

            gemini_role = (
                "model"
                if role == "assistant"
                else "user"
            )

            contents.append(
                types.Content(
                    role=gemini_role,
                    parts=[
                        types.Part.from_text(
                            text=content,
                        ),
                    ],
                )
            )

        if not contents:
            raise LLMUnavailableError(
                "Gemini received no usable structured content."
            )

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_json_schema=schema,
            max_output_tokens=1024,
            thinking_config=types.ThinkingConfig(
                thinking_level="minimal",
            ),
        )

        llm_id = next_llm_call_id()
        request_started = datetime.now(timezone.utc).isoformat()
        config_trace = gemini_config_to_trace_dict(config)

        trace(
            "gemini.structured.request",
            provider=self.name,
            model=self._model,
            purpose="structured",
            llm_call_id=llm_id,
            request_started_at=request_started,
            input_messages=messages,
            schema=schema,
            contents_count=len(contents),
            contents=gemini_contents_to_trace_list(contents),
            config=config_trace,
            structured_output=True,
            tools_configured=config_trace.get(
                "tools_configured",
                False,
            ),
            automatic_function_calling=config_trace.get(
                "automatic_function_calling",
            ),
        )

        try:
            response = (
                self._client.models.generate_content(
                    model=self._model,
                    contents=contents,
                    config=config,
                )
            )

        except Exception as exc:
            message = str(exc).lower()

            trace_exception(
                "gemini.structured.error",
                exc,
                provider=self.name,
                model=self._model,
                llm_call_id=llm_id,
            )

            if (
                "401" in message
                or "403" in message
                or "api key" in message
                or "authentication" in message
            ):
                raise LLMAuthenticationError(
                    "Gemini authentication failed."
                ) from exc

            if (
                "429" in message
                or "quota" in message
                or "rate limit" in message
            ):
                raise LLMRateLimitError(
                    "Gemini rate limit or quota was exceeded."
                ) from exc

            if (
                "timeout" in message
                or "deadline" in message
            ):
                raise LLMTimeoutError(
                    "Gemini request timed out."
                ) from exc

            raise LLMUnavailableError(
                "Gemini structured request failed."
            ) from exc

        latency_ms = (
            time.perf_counter() - started
        ) * 1000

        raw_trace = gemini_response_to_trace_dict(response)

        trace(
            "gemini.structured.response.raw",
            provider=self.name,
            model=self._model,
            llm_call_id=llm_id,
            status="success",
            latency_ms=round(latency_ms, 2),
            raw_response=raw_trace,
            http_requests=1,
            afc_remote_calls="unknown",
            note=(
                "AFC remote call count is not exposed by the "
                "google-genai SDK response object."
            ),
        )

        text = response.text or ""

        if not text.strip():
            raise LLMUnavailableError(
                "Gemini returned an empty structured response."
            )

        usage = response.usage_metadata

        finish_reason = None

        if response.candidates:
            raw_finish_reason = getattr(
                response.candidates[0],
                "finish_reason",
                None,
            )

            if raw_finish_reason is not None:
                finish_reason = getattr(
                    raw_finish_reason,
                    "name",
                    None,
                ) or str(raw_finish_reason)

        llm_response = LLMResponse(
            text=text,
            provider=self.name,
            model=self.model,
            input_tokens=(
                getattr(
                    usage,
                    "prompt_token_count",
                    None,
                )
                if usage is not None
                else None
            ),
            output_tokens=(
                getattr(
                    usage,
                    "candidates_token_count",
                    None,
                )
                if usage is not None
                else None
            ),
            latency_ms=latency_ms,
            finish_reason=finish_reason,
            request_id=getattr(
                response,
                "response_id",
                None,
            ),
        )

        trace(
            "gemini.structured.response.normalized",
            provider=self.name,
            model=self.model,
            llm_call_id=llm_id,
            raw_response=raw_trace,
            normalized=llm_response_to_dict(llm_response),
            finish_reason=finish_reason,
        )

        return llm_response