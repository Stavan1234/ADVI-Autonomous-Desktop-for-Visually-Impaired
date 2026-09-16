from __future__ import annotations

import pytest

from advi.providers import ResilientLLMProvider
from advi.providers.base import LLMProvider, LLMResponse
from advi.providers.errors import LLMRateLimitError, LLMResponseError, LLMTimeoutError


class StubProvider(LLMProvider):
    def __init__(self, name: str, outcome):
        self._name = name
        self.outcome = outcome
        self.calls = 0

    @property
    def name(self):
        return self._name

    @property
    def model(self):
        return f"{self._name}-model"

    def chat(self, messages):
        self.calls += 1
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def response(provider: str, text: str = "ok"):
    return LLMResponse(text=text, provider=provider, model="model")


def test_primary_success_does_not_call_fallback():
    primary = StubProvider("primary", response("primary"))
    fallback = StubProvider("fallback", response("fallback"))
    router = ResilientLLMProvider([primary, fallback])

    result = router.chat([{"role": "user", "content": "hello"}])

    assert result.provider == "primary"
    assert primary.calls == 1
    assert fallback.calls == 0


def test_timeout_falls_back_once():
    primary = StubProvider("primary", LLMTimeoutError("timeout"))
    fallback = StubProvider("fallback", response("fallback"))
    router = ResilientLLMProvider([primary, fallback])

    result = router.chat([])

    assert result.provider == "fallback"
    assert primary.calls == 1
    assert fallback.calls == 1
    assert router.last_attempts[0].error_type == "LLMTimeoutError"
    assert router.last_attempts[-1].success is True


def test_rate_limit_falls_back():
    primary = StubProvider("primary", LLMRateLimitError("quota"))
    fallback = StubProvider("fallback", response("fallback"))
    router = ResilientLLMProvider([primary, fallback])

    assert router.chat([]).provider == "fallback"


def test_malformed_empty_response_falls_back():
    primary = StubProvider("primary", response("primary", ""))
    fallback = StubProvider("fallback", response("fallback", "usable"))
    router = ResilientLLMProvider([primary, fallback])

    assert router.chat([]).text == "usable"
    assert router.last_attempts[0].error_type == "LLMResponseError"


def test_all_provider_errors_surface_last_error():
    primary = StubProvider("primary", LLMTimeoutError("timeout"))
    fallback = StubProvider("fallback", LLMRateLimitError("quota"))
    router = ResilientLLMProvider([primary, fallback])

    with pytest.raises(LLMRateLimitError):
        router.chat([])

    assert len(router.last_attempts) == 2


def test_unexpected_exception_is_not_hidden_by_fallback():
    primary = StubProvider("primary", RuntimeError("bug"))
    fallback = StubProvider("fallback", response("fallback"))
    router = ResilientLLMProvider([primary, fallback])

    with pytest.raises(RuntimeError):
        router.chat([])
    assert fallback.calls == 0
