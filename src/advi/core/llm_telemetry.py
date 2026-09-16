from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LLMCallRecord:
    provider: str
    model: str
    purpose: str

    latency_ms: float | None = None

    input_tokens: int | None = None
    output_tokens: int | None = None

    @property
    def total_tokens(self) -> int | None:
        if (
            self.input_tokens is None
            or self.output_tokens is None
        ):
            return None

        return (
            self.input_tokens
            + self.output_tokens
        )

class LLMTelemetry:
    """Collect LLM call metrics for the current process."""

    def __init__(self) -> None:
        self.calls: list[LLMCallRecord] = []

    def record(
        self,
        response,
        purpose: str,
    ) -> LLMCallRecord:
        record = LLMCallRecord(
            provider=response.provider,
            model=response.model,
            purpose=purpose,
            latency_ms=response.latency_ms,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )

        self.calls.append(record)

        return record

    @property
    def total_calls(self) -> int:
        return len(self.calls)

    @property
    def total_input_tokens(self) -> int:
        return sum(
            call.input_tokens or 0
            for call in self.calls
        )

    @property
    def total_output_tokens(self) -> int:
        return sum(
            call.output_tokens or 0
            for call in self.calls
        )

    @property
    def total_tokens(self) -> int:
        return (
            self.total_input_tokens
            + self.total_output_tokens
        )

    @property
    def total_latency_ms(self) -> float:
        return sum(
            call.latency_ms or 0.0
            for call in self.calls
        )

    def records_since(
        self,
        start_index: int,
    ) -> list[LLMCallRecord]:
        return self.calls[start_index:]