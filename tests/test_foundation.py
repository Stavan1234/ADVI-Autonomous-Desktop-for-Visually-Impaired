from advi.core.executor import ExecutionResult
from _pytest import cacheprovider
from _pytest import cacheprovider
from _pytest import cacheprovider
from advi.core.config import load_settings
from advi.core.runtime import Runtime
from advi.io.tts import clean_for_speech
from advi.io.output import AdviResponse, OutputManager
from advi.providers import LLMProvider, LLMResponse
from unittest.mock import Mock, patch
from advi.core.conversation import ConversationEngine
from advi.memory.long_term import LongTermMemory
from advi.memory.short_term import ShortTermMemory
from advi.memory.session import SessionBuffer
from advi.memory.retriever import MemoryRetriever
from advi.core.task import TaskStatus

from groq import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    RateLimitError,
)

from advi.providers import (
    GroqProvider,
    LLMAuthenticationError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
)

def test_response_has_separate_speech_representation():
    response = AdviResponse(
        "## Today's plan\n\n"
        "| Task | Time |\n"
        "|---|---|\n"
        "| Study | 2 PM |\n"
        "| Gym | 6 PM |\n"
        "\n"
        "**Priority:** Study first."
    )

    assert "##" in response.for_display()
    assert "|" in response.for_display()

    speech = response.for_speech()

    assert "Today's plan" in speech
    assert "Study" in speech
    assert "2 PM" in speech
    assert "Gym" in speech
    assert "6 PM" in speech
    assert "##" not in speech

def test_settings_load_without_secrets(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    settings = load_settings()

    assert settings.groq_api_key is None
    assert settings.gemini_api_key is None
    assert settings.piper_exe.name == "piper.exe"


def test_runtime_start_and_shutdown(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    runtime = Runtime.create()
    runtime.start()

    assert runtime.started is True

    runtime.shutdown()

    assert runtime.started is False


def test_speech_cleaning():
    assert clean_for_speech(
        "**Hello** [Advi](https://example.com)..."
    ) == "Hello Advi,"


def test_response_speech_removes_markdown():
    response = AdviResponse(
        "## Hello\n\n"
        "This is **important** and [useful](https://example.com).\n\n"
        "- First item\n"
        "- Second item"
    )

    speech = response.for_speech()

    assert "##" not in speech
    assert "**" not in speech
    assert "https://" not in speech
    assert "First item" in speech
    assert "Second item" in speech


def test_response_speech_handles_table():
    response = AdviResponse(
        "| Task | Time |\n"
        "|---|---|\n"
        "| Study | 2 PM |\n"
        "| Gym | 6 PM |"
    )

    speech = response.for_speech()

    assert "Task: Study; Time: 2 PM." in speech
    assert "Task: Gym; Time: 6 PM." in speech


def test_empty_response_produces_no_speech():
    response = AdviResponse("")

    assert response.for_display() == ""
    assert response.for_speech() == ""

class FakeTTS:
    def __init__(self, result: bool) -> None:
        self.result = result
        self.spoken: list[str] = []

    def speak(self, text: str) -> bool:
        self.spoken.append(text)
        return self.result


def test_output_manager_reports_tts_failure():
    fake_tts = FakeTTS(False)
    output = OutputManager(tts=fake_tts)

    result = output.deliver(
        AdviResponse("Hello. This is a test.")
    )

    assert result is False
    assert fake_tts.spoken == ["Hello. This is a test."]


def test_output_manager_reports_success():
    fake_tts = FakeTTS(True)
    output = OutputManager(tts=fake_tts)

    result = output.deliver(
        AdviResponse("Hello. This is a test.")
    )

    assert result is True
    assert fake_tts.spoken == ["Hello. This is a test."]



def test_llm_response_contract():
    response = LLMResponse(
        text="Hello.",
        provider="test",
        model="test-model",
        input_tokens=10,
        output_tokens=5,
        latency_ms=42.5,
        finish_reason="stop",
        request_id="test-request",
    )

    assert response.text == "Hello."
    assert response.provider == "test"
    assert response.model == "test-model"
    assert response.input_tokens == 10
    assert response.output_tokens == 5
    assert response.latency_ms == 42.5
    assert response.finish_reason == "stop"
    assert response.request_id == "test-request"

def test_llm_provider_is_abstract():
    assert issubclass(LLMProvider, object)


def test_groq_provider_properties():
    provider = GroqProvider(
        api_key="test-key",
        model="test-model",
    )

    assert provider.name == "groq"
    assert provider.model == "test-model"


def test_groq_authentication_error_is_normalized():
    provider = GroqProvider(
        api_key="test-key",
        model="test-model",
    )

    with patch.object(
        provider._client.chat.completions,
        "create",
        side_effect=AuthenticationError(
            "bad key",
            response=Mock(status_code=401),
            body=None,
        ),
    ):
        try:
            provider.chat(
                [{"role": "user", "content": "hello"}]
            )
            assert False
        except LLMAuthenticationError as exc:
            assert "authentication" in str(exc).lower()


def test_groq_rate_limit_error_is_normalized():
    provider = GroqProvider(
        api_key="test-key",
        model="test-model",
    )

    with patch.object(
        provider._client.chat.completions,
        "create",
        side_effect=RateLimitError(
            "rate limited",
            response=Mock(status_code=429),
            body=None,
        ),
    ):
        try:
            provider.chat(
                [{"role": "user", "content": "hello"}]
            )
            assert False
        except LLMRateLimitError as exc:
            assert "rate limit" in str(exc).lower()


def test_groq_timeout_error_is_normalized():
    provider = GroqProvider(
        api_key="test-key",
        model="test-model",
    )

    with patch.object(
        provider._client.chat.completions,
        "create",
        side_effect=APITimeoutError(
            request=Mock(),
        ),
    ):
        try:
            provider.chat(
                [{"role": "user", "content": "hello"}]
            )
            assert False
        except LLMTimeoutError as exc:
            assert "timed out" in str(exc).lower()


def test_groq_connection_error_is_normalized():
    provider = GroqProvider(
        api_key="test-key",
        model="test-model",
    )

    with patch.object(
        provider._client.chat.completions,
        "create",
        side_effect=APIConnectionError(
            request=Mock(),
        ),
    ):
        try:
            provider.chat(
                [{"role": "user", "content": "hello"}]
            )
            assert False
        except LLMUnavailableError as exc:
            assert "connect" in str(exc).lower()


def test_groq_success_is_normalized():
    provider = GroqProvider(
        api_key="test-key",
        model="test-model",
    )

    mock_response = Mock()

    mock_response.choices = [
        Mock(
            message=Mock(content="Hello, Advi."),
            finish_reason="stop",
        )
    ]

    mock_response.usage = Mock(
        prompt_tokens=12,
        completion_tokens=7,
    )

    mock_response.id = "req-test-123"

    with patch.object(
        provider._client.chat.completions,
        "create",
        return_value=mock_response,
    ):
        response = provider.chat(
            [{"role": "user", "content": "hello"}]
        )

    assert response.text == "Hello, Advi."
    assert response.provider == "groq"
    assert response.model == "test-model"
    assert response.input_tokens == 12
    assert response.output_tokens == 7
    assert response.finish_reason == "stop"
    assert response.request_id == "req-test-123"
    assert response.latency_ms is not None            


class FakeProvider:
    name = "fake"
    model = "fake-model"

    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    def chat(self, messages):
        self.messages = messages

        return LLMResponse(
            text="Hello from the fake model.",
            provider=self.name,
            model=self.model,
        )


def test_conversation_engine_creates_response():
    provider = FakeProvider()
    engine = ConversationEngine(provider)

    response = engine.respond("Hello Advi.")

    assert response.text == "Hello from the fake model."
    assert provider.messages[-1] == {
        "role": "user",
        "content": "Hello Advi.",
    }

    assert provider.messages[0]["role"] == "system"
    assert "You are ADVI" in provider.messages[0]["content"]
    assert "Be concise by default" in provider.messages[0]["content"]


def test_conversation_engine_ignores_empty_input():
    provider = FakeProvider()
    engine = ConversationEngine(provider)

    response = engine.respond("   ")

    assert response.text == ""
    assert provider.messages == []

def test_long_term_memory_persists(tmp_path):
    database = tmp_path / "memory.db"

    memory = LongTermMemory(database)

    memory.remember(
        "user",
        "name",
        "Stavan",
    )

    # Simulate ADVI shutting down.
    memory = LongTermMemory(database)

    result = memory.recall(
        "user",
        "name",
    )

    assert result is not None
    assert result.value == "Stavan"    


def test_long_term_memory_updates_existing_value(tmp_path):
    database = tmp_path / "memory.db"

    memory = LongTermMemory(database)

    memory.remember(
        "user",
        "name",
        "Stavan",
    )

    memory.remember(
        "user",
        "name",
        "Stavan Kalkumbe",
    )

    result = memory.recall(
        "user",
        "name",
    )

    assert result is not None
    assert result.value == "Stavan Kalkumbe"

def test_session_buffer_stages_evicted_messages():
    memory = ShortTermMemory(max_messages=2)
    buffer = SessionBuffer()

    buffer.add(
        memory.add("user", "one")
    )

    buffer.add(
        memory.add("assistant", "two")
    )

    evicted = memory.add("user", "three")
    buffer.add(evicted)

    assert memory.get_messages() == [
        {"role": "assistant", "content": "two"},
        {"role": "user", "content": "three"},
    ]

    assert buffer.messages == [
        {"role": "user", "content": "one"},
    ]   
    
def test_memory_search_handles_possessive_query(tmp_path):
    memory = LongTermMemory(
        tmp_path / "memory.db"
    )

    memory.remember(
        "family",
        "father",
        "Devdan Kalkumbe",
        "The user's father is Devdan Kalkumbe.",
        0.98,
    )

    results = memory.search(
        "What is my father's name?"
    )

    assert any(
        item.key == "father"
        and item.value == "Devdan Kalkumbe"
        for item in results
    )     

def test_memory_search_handles_question_punctuation(tmp_path):
    memory = LongTermMemory(
        tmp_path / "memory.db"
    )

    memory.remember(
        "family",
        "father",
        "Devdan Kalkumbe",
        "The user's father is Devdan Kalkumbe.",
        0.98,
    )

    results = memory.search(
        "father?"
    )

    assert any(
        item.key == "father"
        for item in results
    )

def test_memory_update_preserves_history(tmp_path):
    memory = LongTermMemory(
        tmp_path / "memory.db"
    )

    memory.remember(
        "user",
        "institution",
        "FCRIT Vashi",
        "The user studies at FCRIT Vashi.",
        0.98,
    )

    memory.remember(
        "user",
        "institution",
        "VJTI",
        "The user studies at VJTI.",
        0.98,
    )

    current = memory.recall(
        "user",
        "institution",
    )

    assert current is not None
    assert current.value == "VJTI"

    history = memory.history(
        "user",
        "institution",
    )

    assert len(history) == 1
    assert history[0].value == "FCRIT Vashi"

def test_memory_update_does_not_create_history_for_same_fact(
    tmp_path,
):
    memory = LongTermMemory(
        tmp_path / "memory.db"
    )

    memory.remember(
        "user",
        "name",
        "Stavan Kalkumbe",
        "The user's name is Stavan Kalkumbe.",
        0.98,
    )

    memory.remember(
        "user",
        "name",
        "Stavan Kalkumbe",
        "The user's name is Stavan Kalkumbe.",
        0.98,
    )

    history = memory.history(
        "user",
        "name",
    )

    assert history == []       

def test_memory_retriever_finds_paraphrased_fact(tmp_path):
    memory = LongTermMemory(
        tmp_path / "memory.db"
    )

    memory.remember(
        "user",
        "institution",
        "FCRIT Vashi",
        "The user studies at FCRIT Vashi.",
        0.98,
    )

    retriever = MemoryRetriever(memory)

    results = retriever.search(
        "where do I study",
        limit=5,
    )

    assert results

    assert any(
        result.memory.key == "institution"
        and result.memory.value == "FCRIT Vashi"
        for result in results
    )


def test_relationship_search_finds_direct_relationship(
    tmp_path,
):
    memory = LongTermMemory(
        tmp_path / "memory.db"
    )

    memory.remember_relationship(
        "user",
        "father",
        "Devdan Kalkumbe",
        0.98,
    )

    results = memory.search_relationships(
        "What is my father's name?"
    )

    assert results
    assert any(
        relationship.object == "Devdan Kalkumbe"
        for relationship in results
    )


def test_relationship_search_supports_multi_hop_candidates(
    tmp_path,
):
    memory = LongTermMemory(
        tmp_path / "memory.db"
    )

    memory.remember_relationship(
        "user",
        "uncle",
        "Pradeep",
        0.98,
    )

    memory.remember_relationship(
        "Pradeep",
        "daughter",
        "Ramanika",
        0.98,
    )

    memory.remember_relationship(
        "Ramanika",
        "younger sister",
        "Aaradhana",
        0.98,
    )

    results = memory.search_relationships(
        "Who is Ramanika?"
    )

    objects = {
        relationship.object
        for relationship in results
    }

    assert "Ramanika" in objects


def test_memory_update_keeps_current_value(
    tmp_path,
):
    memory = LongTermMemory(
        tmp_path / "memory.db"
    )

    memory.remember(
        "user",
        "institution",
        "FCRIT Vashi",
        "The user studies at FCRIT Vashi.",
        0.90,
    )

    memory.remember(
        "user",
        "institution",
        "VJTI",
        "The user studies at VJTI.",
        0.95,
    )

    current = memory.recall(
        "user",
        "institution"
    )

    assert current is not None
    assert current.value == "VJTI"

    history = memory.history(
        "user",
        "institution"
    )

    assert len(history) == 1
    assert history[0].value == "FCRIT Vashi"


def test_same_memory_does_not_create_history(
    tmp_path,
):
    memory = LongTermMemory(
        tmp_path / "memory.db"
    )

    memory.remember(
        "user",
        "name",
        "Stavan Kalkumbe",
        "The user's name is Stavan Kalkumbe.",
        0.98,
    )

    memory.remember(
        "user",
        "name",
        "Stavan Kalkumbe",
        "The user's name is Stavan Kalkumbe.",
        0.98,
    )

    assert memory.history(
        "user",
        "name"
    ) == [] 

def test_related_entities_supports_two_hop_relationships(
    tmp_path,
):
    memory = LongTermMemory(
        tmp_path / "memory.db"
    )

    memory.remember_relationship(
        "user",
        "uncle",
        "Pradeep",
        0.98,
    )

    memory.remember_relationship(
        "Pradeep",
        "daughter",
        "Ramanika",
        0.98,
    )

    results = memory.related_entities(
        "user",
        max_hops=2,
    )

    triples = {
        (
            item.subject,
            item.relation,
            item.object,
        )
        for item in results
    }

    assert (
        ("user", "uncle", "Pradeep")
        in triples
    )

    assert (
        ("Pradeep", "daughter", "Ramanika")
        in triples
    )

def test_memory_conflict_prefers_higher_confidence(
    tmp_path,
):
    memory = LongTermMemory(
        tmp_path / "memory.db"
    )

    memory.remember(
        "user",
        "institution",
        "Old College",
        "The user studies at Old College.",
        0.95,
    )

    memory.remember(
        "user",
        "institution",
        "New College",
        "The user studies at New College.",
        0.40,
    )

    current = memory.recall(
        "user",
        "institution",
    )

    assert current is not None
    assert current.value == "Old College"

    assert memory.history(
        "user",
        "institution",
    ) == []

def test_memory_conflict_accepts_higher_confidence_update(
    tmp_path,
):
    memory = LongTermMemory(
        tmp_path / "memory.db"
    )

    memory.remember(
        "user",
        "institution",
        "Old College",
        "The user studies at Old College.",
        0.80,
    )

    memory.remember(
        "user",
        "institution",
        "New College",
        "The user studies at New College.",
        0.95,
    )

    current = memory.recall(
        "user",
        "institution",
    )

    assert current is not None
    assert current.value == "New College"

    history = memory.history(
        "user",
        "institution",
    )

    assert len(history) == 1
    assert history[0].value == "Old College"

def test_identical_memory_does_not_create_history(
    tmp_path,
):
    memory = LongTermMemory(
        tmp_path / "memory.db"
    )

    memory.remember(
        "user",
        "name",
        "Stavan",
        "The user's name is Stavan.",
        0.90,
    )

    memory.remember(
        "user",
        "name",
        "Stavan",
        "The user's name is Stavan.",
        0.95,
    )

    current = memory.recall(
        "user",
        "name",
    )

    assert current is not None
    assert current.confidence == 0.95

    assert memory.history(
        "user",
        "name",
    ) == []

def test_memory_conflict_equal_confidence_replaces_old(
    tmp_path,
):
    memory = LongTermMemory(
        tmp_path / "memory.db"
    )

    memory.remember(
        "user",
        "institution",
        "Old College",
        "The user studies at Old College.",
        0.90,
    )

    memory.remember(
        "user",
        "institution",
        "New College",
        "The user studies at New College.",
        0.90,
    )

    current = memory.recall(
        "user",
        "institution",
    )

    assert current is not None
    assert current.value == "New College"

    history = memory.history(
        "user",
        "institution",
    )

    assert len(history) == 1
    assert history[0].value == "Old College"       


def test_advi_identity_is_present():
    from advi.core.personality import build_advi_system_prompt

    prompt = build_advi_system_prompt()

    assert "ADVI" in prompt
    assert "Autonomous Desktop for the Visually Impaired" in prompt
    assert "Do not identify yourself as ChatGPT" in prompt


def test_advi_personality_is_concise_by_default():
    from advi.core.personality import build_advi_system_prompt

    prompt = build_advi_system_prompt()

    assert "Be concise by default" in prompt
    assert "Do not over-explain" in prompt


def test_advi_personality_is_speech_friendly():
    from advi.core.personality import build_advi_system_prompt

    prompt = build_advi_system_prompt()

    assert "speech-friendly" in prompt
    assert "Do not read Markdown syntax literally" in prompt             

def test_response_policy_defaults_to_concise():
    from advi.core.response_policy import detect_response_mode

    assert detect_response_mode("What is Python?") == "concise"


def test_response_policy_detects_detailed_request():
    from advi.core.response_policy import detect_response_mode

    assert detect_response_mode(
        "Explain Python in detail."
    ) == "detailed"


def test_response_policy_detects_brief_request():
    from advi.core.response_policy import detect_response_mode

    assert detect_response_mode(
        "What is Python? Keep it short."
    ) == "concise"


def test_response_policy_builds_instruction():
    from advi.core.response_policy import build_response_policy

    policy = build_response_policy("Explain this step by step.")

    assert "DETAILED" in policy

def test_capability_registry_contains_core_capabilities():
    from advi.core.capabilities import (
        CAPABILITIES,
        CapabilityStatus,
    )

    assert "conversation" in CAPABILITIES
    assert "memory" in CAPABILITIES
    assert "session_continuity" in CAPABILITIES
    assert "speech_output" in CAPABILITIES

    assert (
        CAPABILITIES["memory"].status
        == CapabilityStatus.AVAILABLE
    )


def test_capability_registry_marks_unimplemented_features_unavailable():
    from advi.core.capabilities import (
        CAPABILITIES,
        CapabilityStatus,
    )

    assert (
        CAPABILITIES["web_search"].status
        == CapabilityStatus.UNAVAILABLE
    )

    assert (
        CAPABILITIES["vision"].status
        == CapabilityStatus.UNAVAILABLE
    )

    assert (
        CAPABILITIES["desktop_control"].status
        == CapabilityStatus.UNAVAILABLE
    )


def test_get_capability_is_case_insensitive():
    from advi.core.capabilities import get_capability

    capability = get_capability(" MEMORY ")

    assert capability is not None
    assert capability.name == "memory"


def test_capability_summary_contains_status_groups():
    from advi.core.capabilities import capability_summary

    summary = capability_summary()

    assert "Available capabilities:" in summary
    assert "Unavailable capabilities:" in summary
    assert "memory:" in summary
    assert "web_search:" in summary


def test_capability_can_use_reports_actual_status():
    from advi.core.capabilities import can_use

    assert can_use("conversation")
    assert can_use("memory")
    assert not can_use("web_search")
    assert not can_use("vision")


def test_capability_prompt_contains_available_and_unavailable_state():
    from advi.core.capabilities import capability_for_prompt

    prompt = capability_for_prompt()

    assert "Conversation: available" in prompt
    assert "Long-term memory: available" in prompt
    assert "Web search: unavailable" in prompt
    assert "Screen/vision understanding: unavailable" in prompt
    assert "Never claim to have an unavailable capability." in prompt      

def test_intent_preserves_core_fields():
    from advi.core.intent import Intent, IntentType

    intent = Intent(
        type=IntentType.MEMORY_RETRIEVAL,
        confidence=0.95,
        original_input="What is my father's name?",
        target="father",
        entities={
            "relationship": "father",
        },
    )

    assert intent.type == IntentType.MEMORY_RETRIEVAL
    assert intent.confidence == 0.95
    assert intent.target == "father"
    assert intent.entities["relationship"] == "father"


def test_intent_confidence_is_clamped():
    from advi.core.intent import Intent, IntentType

    low = Intent(
        type=IntentType.UNKNOWN,
        confidence=-2,
        original_input="test",
    )

    high = Intent(
        type=IntentType.UNKNOWN,
        confidence=5,
        original_input="test",
    )

    assert low.confidence == 0.0
    assert high.confidence == 1.0


def test_intent_type_contains_initial_core_categories():
    from advi.core.intent import IntentType

    assert IntentType.CONVERSATION.value == "conversation"
    assert IntentType.MEMORY_RETRIEVAL.value == "memory_retrieval"
    assert IntentType.MEMORY_UPDATE.value == "memory_update"
    assert IntentType.CAPABILITY_QUERY.value == "capability_query"
    assert IntentType.IDENTITY_QUERY.value == "identity_query"
    assert IntentType.SYSTEM_CONTROL.value == "system_control"
    assert IntentType.UNKNOWN.value == "unknown"          


def test_intent_detector_parses_valid_json():
    from advi.core.intent_detector import IntentDetector
    from advi.core.intent import IntentType

    class FakeProvider:
        def chat(self, messages):
            class Result:
                text = """
                {
                    "intent": "memory_retrieval",
                    "confidence": 0.96,
                    "target": "father",
                    "entities": {
                        "relationship": "father"
                    },
                    "parameters": {}
                }
                """

            return Result()

    detector = IntentDetector(FakeProvider())

    result = detector.detect(
        "What is my father's name?"
    )

    assert result.type == IntentType.MEMORY_RETRIEVAL
    assert result.confidence == 0.96
    assert result.target == "father"
    assert result.entities["relationship"] == "father"


def test_intent_detector_rejects_invalid_intent():
    from advi.core.intent_detector import IntentDetector
    from advi.core.intent import IntentType

    class FakeProvider:
        def chat(self, messages):
            class Result:
                text = """
                {
                    "intent": "make_me_coffee",
                    "confidence": 0.99,
                    "target": null,
                    "entities": {},
                    "parameters": {}
                }
                """

            return Result()

    detector = IntentDetector(FakeProvider())

    result = detector.detect(
        "Make me coffee."
    )

    assert result.type == IntentType.UNKNOWN


def test_intent_detector_handles_invalid_json():
    from advi.core.intent_detector import IntentDetector
    from advi.core.intent import IntentType

    class FakeProvider:
        def chat(self, messages):
            class Result:
                text = "this is not json"

            return Result()

    detector = IntentDetector(FakeProvider())

    result = detector.detect(
    "Can you help me figure something out?"
)

    assert result.type == IntentType.UNKNOWN
    assert result.confidence == 0.0


def test_intent_detector_handles_empty_input():
    from advi.core.intent_detector import IntentDetector
    from advi.core.intent import IntentType

    class FakeProvider:
        def chat(self, messages):
            raise AssertionError(
                "Provider should not be called for empty input."
            )

    detector = IntentDetector(FakeProvider())

    result = detector.detect("   ")

    assert result.type == IntentType.UNKNOWN
    assert result.confidence == 1.0    

def test_memory_resolver_parses_create():
    from advi.core.memory_resolver import (
        MemoryOperation,
        MemoryResolver,
    )

    class FakeProvider:
        def chat(self, messages):
            class Result:
                text = """
                {
                    "operation": "create",
                    "category": "user",
                    "key": "favorite_color",
                    "value": "blue",
                    "statement": "The user's favorite color is blue.",
                    "confidence": 0.94,
                    "reason": "This is a new durable preference.",
                    "entities": {}
                }
                """

            return Result()

    class FakeMemory:
        def search(self, query, limit=8):
            return []

    resolver = MemoryResolver(
        FakeProvider(),
        FakeMemory(),
    )

    result = resolver.resolve(
        "Remember that my favorite color is blue."
    )

    assert result.operation == MemoryOperation.CREATE
    assert result.category == "user"
    assert result.key == "favorite_color"
    assert result.value == "blue"
    assert result.confidence == 0.94


def test_memory_resolver_parses_update():
    from advi.core.memory_resolver import (
        MemoryOperation,
        MemoryResolver,
    )

    class FakeProvider:
        def chat(self, messages):
            class Result:
                text = """
                {
                    "operation": "update",
                    "category": "user",
                    "key": "institution",
                    "value": "New College",
                    "statement": "The user studies at New College.",
                    "confidence": 0.97,
                    "reason": "The user corrected their institution.",
                    "entities": {}
                }
                """

            return Result()

    class FakeMemory:
        def search(self, query, limit=8):
            return []

    resolver = MemoryResolver(
        FakeProvider(),
        FakeMemory(),
    )

    result = resolver.resolve(
        "I don't study at Old College anymore. "
        "I study at New College now."
    )

    assert result.operation == MemoryOperation.UPDATE
    assert result.key == "institution"
    assert result.value == "New College"


def test_memory_resolver_ignores_incomplete_mutation():
    from advi.core.memory_resolver import (
        MemoryOperation,
        MemoryResolver,
    )

    class FakeProvider:
        def chat(self, messages):
            class Result:
                text = """
                {
                    "operation": "update",
                    "category": null,
                    "key": null,
                    "value": null,
                    "statement": null,
                    "confidence": 0.8,
                    "reason": "Not enough information.",
                    "entities": {}
                }
                """

            return Result()

    class FakeMemory:
        def search(self, query, limit=8):
            return []

    resolver = MemoryResolver(
        FakeProvider(),
        FakeMemory(),
    )

    result = resolver.resolve(
        "Remember that thing I told you."
    )

    assert result.operation == MemoryOperation.IGNORE
    assert result.category is None


def test_memory_resolver_handles_invalid_json():
    from advi.core.memory_resolver import (
        MemoryOperation,
        MemoryResolver,
    )

    class FakeProvider:
        def chat(self, messages):
            class Result:
                text = "not json"

            return Result()

    class FakeMemory:
        def search(self, query, limit=8):
            return []

    resolver = MemoryResolver(
        FakeProvider(),
        FakeMemory(),
    )

    result = resolver.resolve(
        "Remember my favorite color is blue."
    )

    assert result.operation == MemoryOperation.IGNORE    

def test_intent_handler_creates_memory():
    from advi.core.intent import (
        Intent,
        IntentType,
    )
    from advi.core.intent_handler import IntentHandler
    from advi.core.memory_resolver import (
        MemoryDecision,
        MemoryOperation,
    )

    class FakeDetector:
        def detect(self, user_input):
            return Intent(
                type=IntentType.MEMORY_UPDATE,
                confidence=0.98,
                original_input=user_input,
            )

    class FakeResolver:
        def resolve(self, user_input):
            return MemoryDecision(
                operation=MemoryOperation.CREATE,
                category="user",
                key="favorite_color",
                value="blue",
                statement=(
                    "The user's favorite color is blue."
                ),
                confidence=0.95,
            )

    class FakeMemory:
        def __init__(self):
            self.saved = []

        def remember(
            self,
            category,
            key,
            value,
            statement,
            confidence,
        ):
            self.saved.append(
                {
                    "category": category,
                    "key": key,
                    "value": value,
                    "statement": statement,
                    "confidence": confidence,
                }
            )

    memory = FakeMemory()

    handler = IntentHandler(
        detector=FakeDetector(),
        memory_resolver=FakeResolver(),
        memory=memory,
    )

    intent, decision = handler.handle(
        "Remember that my favorite color is blue."
    )

    assert intent.type == IntentType.MEMORY_UPDATE
    assert decision.operation == MemoryOperation.CREATE

    assert memory.saved == [
        {
            "category": "user",
            "key": "favorite_color",
            "value": "blue",
            "statement": (
                "The user's favorite color is blue."
            ),
            "confidence": 0.95,
        }
    ]


def test_intent_handler_does_not_write_for_non_memory_intent():
    from advi.core.intent import (
        Intent,
        IntentType,
    )
    from advi.core.intent_handler import IntentHandler

    class FakeDetector:
        def detect(self, user_input):
            return Intent(
                type=IntentType.CONVERSATION,
                confidence=0.98,
                original_input=user_input,
            )

    class FakeResolver:
        def resolve(self, user_input):
            raise AssertionError(
                "Memory resolver must not run."
            )

    class FakeMemory:
        def remember(self, **kwargs):
            raise AssertionError(
                "Memory must not be modified."
            )

    handler = IntentHandler(
        detector=FakeDetector(),
        memory_resolver=FakeResolver(),
        memory=FakeMemory(),
    )

    intent, decision = handler.handle(
        "Hey ADVI, how are you?"
    )

    assert intent.type == IntentType.CONVERSATION
    assert decision is None


def test_intent_handler_ignores_non_mutating_memory_decision():
    from advi.core.intent import (
        Intent,
        IntentType,
    )
    from advi.core.intent_handler import IntentHandler
    from advi.core.memory_resolver import (
        MemoryDecision,
        MemoryOperation,
    )

    class FakeDetector:
        def detect(self, user_input):
            return Intent(
                type=IntentType.MEMORY_UPDATE,
                confidence=0.9,
                original_input=user_input,
            )

    class FakeResolver:
        def resolve(self, user_input):
            return MemoryDecision(
                operation=MemoryOperation.IGNORE,
                category=None,
                key=None,
                value=None,
                statement=None,
                confidence=0.0,
                reason="Not durable.",
            )

    class FakeMemory:
        def remember(self, **kwargs):
            raise AssertionError(
                "Ignored memory decision must not be saved."
            )

    handler = IntentHandler(
        detector=FakeDetector(),
        memory_resolver=FakeResolver(),
        memory=FakeMemory(),
    )

    intent, decision = handler.handle(
        "Remember that I am tired today."
    )

    assert intent.type == IntentType.MEMORY_UPDATE
    assert decision.operation == MemoryOperation.IGNORE    

def test_intent_detector_uses_llm_for_capability_query():
    from advi.core.intent import IntentType
    from advi.core.intent_detector import IntentDetector

    class FakeProvider:
        def __init__(self):
            self.calls = 0

        def chat(self, messages):
            self.calls += 1

            class Result:
                text = """
                {
                    "intent": "capability_query",
                    "confidence": 0.96,
                    "target": null,
                    "entities": {},
                    "parameters": {}
                }
                """

            return Result()

    provider = FakeProvider()

    result = IntentDetector(
        provider
    ).detect("What can you do?")

    assert result.type == IntentType.CAPABILITY_QUERY
    assert provider.calls == 1


def test_intent_detector_extracts_memory_target():
    from advi.core.intent import IntentType
    from advi.core.intent_detector import IntentDetector

    class FakeProvider:
        def chat(self, messages):
            class Result:
                text = """
                {
                    "intent": "memory_retrieval",
                    "confidence": 0.97,
                    "target": "favorite_colour",
                    "entities": {
                        "property": "favorite_colour"
                    },
                    "parameters": {}
                }
                """

            return Result()

    result = IntentDetector(
        FakeProvider()
    ).detect(
        "Which colour do I like most?"
    )

    assert result.type == IntentType.MEMORY_RETRIEVAL
    assert result.target == "favorite_colour"   

def test_conversation_engine_can_detect_intent_without_changing_response():
    from advi.core.conversation import ConversationEngine
    from advi.core.intent import Intent, IntentType

    class FakeProvider:
        def __init__(self):
            self.messages = []

        def chat(self, messages):
            self.messages = messages

            class Result:
                text = "Hello from the fake model."

            return Result()

    class FakeIntentDetector:
        def __init__(self):
            self.inputs = []

        def detect(self, text):
            self.inputs.append(text)

            return Intent(
                type=IntentType.CONVERSATION,
                confidence=0.99,
                original_input=text,
            )

    provider = FakeProvider()
    detector = FakeIntentDetector()

    engine = ConversationEngine(
        provider=provider,
        intent_detector=detector,
    )

    response = engine.respond(
        "Hello Advi."
    )

    assert response.text == (
        "Hello from the fake model."
    )

    assert detector.inputs == [
        "Hello Advi."
    ]    

def test_conversation_engine_uses_final_llm_for_memory_retrieval():
    from advi.core.conversation import ConversationEngine
    from advi.core.intent import Intent, IntentType

    class FakeProvider:
        def __init__(self):
            self.calls = []

        def chat(self, messages):
            self.calls.append(messages)

            class Result:
                text = (
                    "Your favourite colour is blue."
                )

            return Result()

    class FakeIntentDetector:
        def detect(self, text):
            return Intent(
                type=IntentType.MEMORY_RETRIEVAL,
                confidence=0.99,
                original_input=text,
                target="favorite_colour",
            )

    class FakeMemory:
        def recall(self, category, key):
            if key == "favorite_colour":
                class Memory:
                    statement = (
                        "The user's favourite colour is blue."
                    )
                    value = "blue"

                return Memory()

            return None

        def search_relationships(self, text, limit=12):
            return []



    class FakeRetriever:
        memory = FakeMemory()

        def search(self, text, limit=12):
            return []

        @property
        def memory(self):
            return self._memory

    retriever = FakeRetriever()
    retriever._memory = FakeMemory()

    provider = FakeProvider()

    engine = ConversationEngine(
        provider=provider,
        retriever=retriever,
        intent_detector=FakeIntentDetector(),
    )

    response = engine.respond(
        "What is my favourite colour?"
    )

    assert response.text == (
        "Your favourite colour is blue."
    )

    assert len(provider.calls) == 1

    system_message = provider.calls[0][0]

    assert "Exact requested memory" in (
        system_message["content"]
    )
    assert "favourite colour is blue" in (
        system_message["content"]
    )  

def test_memory_answer_is_formatted_for_speech():
    from advi.core.local_responses import format_memory_answer

    assert (
        format_memory_answer(
            "What is my father's name?",
            "Devdan Kalkumbe",
        )
        == "Your father's name is Devdan Kalkumbe."
    )    

def test_identity_query_uses_final_llm():
    from advi.core.conversation import ConversationEngine
    from advi.core.intent import Intent, IntentType

    class FakeProvider:
        def __init__(self):
            self.calls = 0

        def chat(self, messages):
            self.calls += 1

            class Result:
                text = "I am ADVI."

            return Result()

    class FakeIntentDetector:
        def detect(self, text):
            return Intent(
                type=IntentType.IDENTITY_QUERY,
                confidence=0.99,
                original_input=text,
            )

    provider = FakeProvider()

    engine = ConversationEngine(
        provider=provider,
        intent_detector=FakeIntentDetector(),
    )

    response = engine.respond(
        "Who are you?"
    )

    assert response.text == "I am ADVI."
    assert provider.calls == 1


def test_capability_query_uses_final_llm():
    from advi.core.conversation import ConversationEngine
    from advi.core.intent import Intent, IntentType

    class FakeProvider:
        def __init__(self):
            self.calls = 0

        def chat(self, messages):
            self.calls += 1

            class Result:
                text = "I can remember information and maintain conversation context."

            return Result()

    class FakeIntentDetector:
        def detect(self, text):
            return Intent(
                type=IntentType.CAPABILITY_QUERY,
                confidence=0.99,
                original_input=text,
            )

    provider = FakeProvider()

    engine = ConversationEngine(
        provider=provider,
        intent_detector=FakeIntentDetector(),
    )

    response = engine.respond(
        "What can you do?"
    )

    assert "remember" in response.text.lower()
    assert provider.calls == 1  

def test_forget_removes_current_and_history(
    tmp_path,
):
    memory = LongTermMemory(
        tmp_path / "memory.db"
    )

    memory.remember(
        "user",
        "institution",
        "Old College",
        "The user studies at Old College.",
        0.70,
    )

    memory.remember(
        "user",
        "institution",
        "New College",
        "The user studies at New College.",
        0.95,
    )

    assert memory.recall(
        "user",
        "institution",
    ) is not None

    assert memory.history(
        "user",
        "institution",
    )

    memory.forget(
        "user",
        "institution",
    )

    assert memory.recall(
        "user",
        "institution",
    ) is None

    assert memory.history(
        "user",
        "institution",
    ) == []    

def test_forget_handler_rejects_weak_match():
    from advi.core.intent_handler import IntentHandler
    from advi.core.intent import Intent, IntentType

    class FakeDetector:
        def detect(self, text):
            return Intent(
                type=IntentType.MEMORY_FORGET,
                confidence=0.99,
                original_input=text,
            )

    class FakeResolver:
        def resolve(self, text):
            raise AssertionError(
                "MemoryResolver should not run."
            )

    class FakeMemory:
        def forget(self, category, key):
            raise AssertionError(
                "Weak match must not delete memory."
            )

    class FakeResult:
        score = 0.30

        class memory:
            category = "user"
            key = "institution"

    class FakeRetriever:
        def search(self, text, limit=5):
            return [FakeResult()]

    handler = IntentHandler(
        detector=FakeDetector(),
        memory_resolver=FakeResolver(),
        memory=FakeMemory(),
        retriever=FakeRetriever(),
    )

    _, forgotten = handler.handle(
        "forget my college"
    )

    assert forgotten is False    

def test_forget_handler_deletes_strong_match():
    from advi.core.intent_handler import IntentHandler
    from advi.core.intent import Intent, IntentType

    class FakeDetector:
        def detect(self, text):
            return Intent(
                type=IntentType.MEMORY_FORGET,
                confidence=0.99,
                original_input=text,
            )

    class FakeResolver:
        def resolve(self, text):
            raise AssertionError(
                "MemoryResolver should not run."
            )

    class FakeMemory:
        def __init__(self):
            self.deleted = None

        def forget(self, category, key):
            self.deleted = (
                category,
                key,
            )

    class FakeResult:
        score = 0.80

        class memory:
            category = "user"
            key = "institution"

    class FakeRetriever:
        def search(self, text, limit=5):
            return [FakeResult()]

    memory = FakeMemory()

    handler = IntentHandler(
        detector=FakeDetector(),
        memory_resolver=FakeResolver(),
        memory=memory,
        retriever=FakeRetriever(),
    )

    _, forgotten = handler.handle(
        "forget my college"
    )

    assert forgotten is True
    assert memory.deleted == (
        "user",
        "institution",
    )  

def test_memory_retrieval_prefers_exact_target_over_semantic_match():
    from advi.core.conversation import ConversationEngine
    from advi.core.intent import Intent, IntentType

    class FakeProvider:
        def __init__(self):
            self.calls = []

        def chat(self, messages):
            self.calls.append(messages)

            class Result:
                text = "Your favourite colour is blue."

            return Result()

    class FakeMemory:
        def recall(self, category, key):
            if category == "user" and key == "favorite_colour":
                class Memory:
                    statement = (
                        "The user's favourite colour is blue."
                    )
                    value = "blue"

                return Memory()

            return None

        def search_relationships(
            self,
            text,
            limit=12,
        ):
            return []

    class FakeResult:
        score = 0.95

        class memory:
            statement = (
                "The user's favourite food is biriyani."
            )
            value = "biriyani"

    class FakeRetriever:
        memory = FakeMemory()

        def search(self, text, limit=8):
            return [FakeResult()]

    class FakeIntentDetector:
        def detect(self, text):
            return Intent(
                type=IntentType.MEMORY_RETRIEVAL,
                confidence=0.99,
                original_input=text,
                target="favorite_colour",
                entities={
                    "property": "favorite_colour",
                },
            )

    engine = ConversationEngine(
        provider=FakeProvider(),
        retriever=FakeRetriever(),
        intent_detector=FakeIntentDetector(),
    )

    response = engine.respond(
        "What is my favourite colour?"
    )

    assert response.text == (
    "Your favourite colour is blue."
    )

def test_identity_query_still_uses_final_llm():
    from advi.core.conversation import ConversationEngine
    from advi.core.intent import Intent, IntentType

    class FakeProvider:
        def __init__(self):
            self.calls = 0

        def chat(self, messages):
            self.calls += 1

            class Result:
                text = "I am ADVI."

            return Result()

    class FakeDetector:
        def detect(self, text):
            return Intent(
                type=IntentType.IDENTITY_QUERY,
                confidence=0.99,
                original_input=text,
            )

    provider = FakeProvider()

    engine = ConversationEngine(
        provider=provider,
        intent_detector=FakeDetector(),
    )

    response = engine.respond(
        "Who are you?"
    )

    assert response.text == "I am ADVI."
    assert provider.calls == 1    

def test_plan_clamps_confidence():
    from advi.core.planner import Plan

    low = Plan(
        goal="test",
        confidence=-1.0,
    )

    high = Plan(
        goal="test",
        confidence=4.0,
    )

    assert low.confidence == 0.0
    assert high.confidence == 1.0


def test_plan_step_preserves_action_and_parameters():
    from advi.core.planner import PlanStep

    step = PlanStep(
        action="memory_update",
        parameters={
            "target": "favorite_colour",
        },
        reason="Store user preference.",
    )

    assert step.action == "memory_update"
    assert step.parameters["target"] == "favorite_colour"


def test_plan_contains_ordered_steps():
    from advi.core.planner import Plan, PlanStep

    plan = Plan(
        goal="compound_task",
        confidence=0.95,
        steps=[
            PlanStep(
                action="memory_update"
            ),
            PlanStep(
                action="memory_retrieval"
            ),
        ],
    )

    assert len(plan.steps) == 2
    assert plan.steps[0].action == "memory_update"
    assert plan.steps[1].action == "memory_retrieval"    

def test_planner_creates_memory_retrieval_plan():
    from advi.core.planner import Planner
    from advi.core.intent import Intent, IntentType

    intent = Intent(
        type=IntentType.MEMORY_RETRIEVAL,
        confidence=0.99,
        original_input="What is my father's name?",
        target="father",
    )

    plan = Planner().create_plan(intent)

    assert plan.status.value == "ready"
    assert plan.goal == "memory_retrieval"
    assert len(plan.steps) == 1
    assert plan.steps[0].action == "memory_retrieval"
    assert plan.steps[0].parameters["target"] == "father"


def test_planner_creates_memory_update_plan():
    from advi.core.planner import Planner
    from advi.core.intent import Intent, IntentType

    intent = Intent(
        type=IntentType.MEMORY_UPDATE,
        confidence=0.98,
        original_input="My favourite colour is blue.",
        target="favorite_colour",
    )

    plan = Planner().create_plan(intent)

    assert plan.goal == "memory_update"
    assert plan.steps[0].action == "memory_update"
    assert plan.steps[0].parameters["target"] == "favorite_colour"


def test_planner_blocks_unknown_intent():
    from advi.core.planner import Planner
    from advi.core.intent import Intent, IntentType

    intent = Intent(
        type=IntentType.UNKNOWN,
        confidence=0.40,
        original_input="something unclear",
    )

    plan = Planner().create_plan(intent)

    assert plan.status.value == "blocked"
    assert plan.steps == []    

def test_executor_rejects_unknown_action():
    from advi.core.executor import Executor
    from advi.core.planner import PlanStep

    result = Executor().execute(
        PlanStep(action="delete_everything")
    )

    assert result.success is False
    assert result.error == "Action is not allowed."


def test_executor_returns_structured_result():
    from advi.core.executor import Executor
    from advi.core.planner import PlanStep

    result = Executor().execute(
        PlanStep(action="capability_query")
    )

    assert result.success is True
    assert result.action == "capability_query"    

def test_task_coordinator_executes_planned_steps():
    from advi.core.task_coordinator import TaskCoordinator
    from advi.core.intent import Intent, IntentType

    intent = Intent(
        type=IntentType.CAPABILITY_QUERY,
        confidence=0.99,
        original_input="What can you do?",
    )

    execution = TaskCoordinator().run(intent)

    assert execution.plan.status.value == "ready"
    assert len(execution.results) == 1
    assert execution.results[0].action == "capability_query"
    assert execution.results[0].success is True


def test_task_coordinator_does_not_execute_blocked_plan():
    from advi.core.task_coordinator import TaskCoordinator
    from advi.core.intent import Intent, IntentType

    intent = Intent(
        type=IntentType.UNKNOWN,
        confidence=0.20,
        original_input="something unclear",
    )

    execution = TaskCoordinator().run(intent)

    assert execution.plan.status.value == "blocked"
    assert execution.results == []    

def test_plan_to_json_is_compact_and_structured():
    from advi.core.planner import (
        Plan,
        PlanStep,
        plan_to_json,
    )

    plan = Plan(
        goal="memory_retrieval",
        confidence=0.97,
        steps=[
            PlanStep(
                action="memory_retrieval",
                parameters={
                    "target": "father",
                },
            )
        ],
    )

    output = plan_to_json(plan)

    assert '"goal":"memory_retrieval"' in output
    assert '"confidence":0.97' in output
    assert '"status":"ready"' in output
    assert '"action":"memory_retrieval"' in output
    assert '"target":"father"' in output    

def test_planner_propagates_original_input():
    from advi.core.planner import Planner
    from advi.core.intent import Intent, IntentType

    original = "What is my father's name?"

    intent = Intent(
        type=IntentType.MEMORY_RETRIEVAL,
        confidence=0.99,
        original_input=original,
        target="father",
    )

    plan = Planner().create_plan(intent)

    assert plan.steps[0].original_input == original    

def test_executor_delegates_memory_update_to_intent_handler():
    from advi.core.executor import Executor
    from advi.core.planner import PlanStep

    class FakeHandler:
        def __init__(self):
            self.received = None

        def handle(self, text):
            self.received = text
            return None, "memory updated"

    handler = FakeHandler()

    executor = Executor(
        intent_handler=handler,
    )

    step = PlanStep(
        action="memory_update",
        original_input="My favourite colour is blue.",
    )

    result = executor.execute(step)

    assert result.success is True
    assert result.data == "memory updated"
    assert (
        handler.received
        == "My favourite colour is blue."
    )

def test_executor_delegates_memory_forget_to_intent_handler():
    from advi.core.executor import Executor
    from advi.core.planner import PlanStep

    class FakeHandler:
        def __init__(self):
            self.received = None

        def handle(self, text):
            self.received = text
            return None, "memory forgotten"

    handler = FakeHandler()

    executor = Executor(
        intent_handler=handler,
    )

    step = PlanStep(
        action="memory_forget",
        original_input="Forget my favourite colour.",
    )

    result = executor.execute(step)

    assert result.success is True
    assert result.data == "memory forgotten"
    assert (
        handler.received
        == "Forget my favourite colour."
    )    

def test_executor_memory_retrieval_uses_original_input():
    from advi.core.executor import Executor
    from advi.core.planner import PlanStep

    class FakeRetriever:
        def __init__(self):
            self.query = None

        def search(self, query, limit=8):
            self.query = query
            return ["memory-result"]

    retriever = FakeRetriever()

    executor = Executor(
        retriever=retriever,
    )

    step = PlanStep(
        action="memory_retrieval",
        parameters={
            "target": "father",
        },
        original_input="What is my father's name?",
    )

    result = executor.execute(step)

    assert result.success is True
    assert result.data == ["memory-result"]
    assert (
        retriever.query
        == "What is my father's name?"
    )   

def test_task_starts_pending():
    from advi.core.task import (
        Task,
        TaskStatus,
    )

    task = Task(
        task_id="task-1"
    )

    assert task.status == TaskStatus.PENDING
    assert task.steps == []
    assert task.error is None     

def test_task_step_starts_pending():
    from advi.core.task import (
        TaskStepState,
        TaskStepStatus,
    )

    step = TaskStepState(
        action="memory_update"
    )

    assert step.status == TaskStepStatus.PENDING
    assert step.result is None
    assert step.error is None   

def test_task_can_track_completed_step():
    from advi.core.task import (
        TaskStepState,
        TaskStepStatus,
    )

    step = TaskStepState(
        action="memory_update"
    )

    step.status = TaskStepStatus.COMPLETED
    step.result = "memory updated"

    assert step.status == TaskStepStatus.COMPLETED
    assert step.result == "memory updated"     

def test_task_manager_creates_task():
    from advi.core.task_manager import TaskManager
    from advi.core.task import TaskStatus

    manager = TaskManager()

    task = manager.create(
        [
            "memory_update",
            "memory_retrieval",
        ]
    )

    assert task.status == TaskStatus.PENDING
    assert len(task.steps) == 2
    assert task.steps[0].action == "memory_update"
    assert task.steps[1].action == "memory_retrieval"

    assert manager.get(task.task_id) is task

def test_task_manager_starts_task():
    from advi.core.task_manager import TaskManager
    from advi.core.task import TaskStatus

    manager = TaskManager()

    task = manager.create(
        ["memory_update"]
    )

    manager.start(task.task_id)

    assert task.status == TaskStatus.RUNNING

def test_task_manager_completes_task():
    from advi.core.task_manager import TaskManager
    from advi.core.task import TaskStatus, TaskStepStatus

    manager = TaskManager()

    task = manager.create(
        ["memory_update"]
    )

    manager.start(task.task_id)
    manager.start_step(task.task_id, 0)

    manager.complete_step(
        task.task_id,
        0,
        "memory updated",
    )

    assert (
        task.steps[0].status
        == TaskStepStatus.COMPLETED
    )

    assert (
        task.steps[0].result
        == "memory updated"
    )

    assert (
        task.status
        == TaskStatus.COMPLETED
    )

def test_task_manager_marks_failed_task():
    from advi.core.task_manager import TaskManager
    from advi.core.task import TaskStatus, TaskStepStatus

    manager = TaskManager()

    task = manager.create(
        ["memory_update"]
    )

    manager.start(task.task_id)
    manager.start_step(task.task_id, 0)

    manager.fail_step(
        task.task_id,
        0,
        "Memory system unavailable.",
    )

    assert (
        task.steps[0].status
        == TaskStepStatus.FAILED
    )

    assert (
        task.status
        == TaskStatus.FAILED
    )

    assert (
        task.error
        == "Memory system unavailable."
    )

def test_task_manager_can_cancel_task():
    from advi.core.task_manager import TaskManager
    from advi.core.task import TaskStatus

    manager = TaskManager()

    task = manager.create(
        ["memory_update"]
    )

    manager.start(task.task_id)
    manager.cancel(task.task_id)

    assert (
        task.status
        == TaskStatus.CANCELLED
    )    

def test_task_coordinator_tracks_execution_state():
    from advi.core.task_coordinator import TaskCoordinator
    from advi.core.task import TaskStatus
    from advi.core.intent import Intent, IntentType

    coordinator = TaskCoordinator()

    intent = Intent(
        type=IntentType.CAPABILITY_QUERY,
        confidence=0.99,
        original_input="What can you do?",
    )

    execution = coordinator.run(intent)

    assert execution.results[0].success is True

    # The coordinator's manager should contain the task.
    tasks = list(
        coordinator.task_manager._tasks.values()
    )

    assert len(tasks) == 1
    assert (
        tasks[0].status
        == TaskStatus.COMPLETED
    )

def test_task_coordinator_marks_failed_execution():
    from advi.core.task_coordinator import TaskCoordinator
    from advi.core.executor import ExecutionResult
    from advi.core.task import TaskStatus
    from advi.core.intent import Intent, IntentType

    class FailingExecutor:
        def execute(self, step):
            return ExecutionResult(
                action=step.action,
                success=False,
                error="Test failure.",
            )

    coordinator = TaskCoordinator(
        executor=FailingExecutor()
    )

    intent = Intent(
        type=IntentType.CAPABILITY_QUERY,
        confidence=0.99,
        original_input="What can you do?",
    )

    execution = coordinator.run(intent)

    assert execution.results[0].success is False

    tasks = list(
        coordinator.task_manager._tasks.values()
    )

    assert len(tasks) == 1
    assert (
        tasks[0].status
        == TaskStatus.FAILED
    )


def test_llm_telemetry_records_call():
    from advi.core.llm_telemetry import LLMTelemetry

    class Response:
        provider = "groq"
        model = "test-model"
        latency_ms = 250.5
        input_tokens = 100
        output_tokens = 25

    telemetry = LLMTelemetry()

    record = telemetry.record(
        Response(),
        "intent_detection",
    )

    assert record.provider == "groq"
    assert record.model == "test-model"
    assert record.purpose == "intent_detection"
    assert record.latency_ms == 250.5
    assert record.input_tokens == 100
    assert record.output_tokens == 25
    assert record.total_tokens == 125    

def test_llm_telemetry_tracks_totals():
    from advi.core.llm_telemetry import LLMTelemetry

    class Response:
        provider = "groq"
        model = "test-model"
        latency_ms = 100.0
        input_tokens = 80
        output_tokens = 20

    telemetry = LLMTelemetry()

    telemetry.record(
        Response(),
        "intent_detection",
    )

    telemetry.record(
        Response(),
        "final_response",
    )

    assert telemetry.total_calls == 2
    assert telemetry.total_input_tokens == 160
    assert telemetry.total_output_tokens == 40
    assert telemetry.total_tokens == 200
    assert telemetry.total_latency_ms == 200.0    

def test_llm_telemetry_records_since_index():
    from advi.core.llm_telemetry import LLMTelemetry

    class Response:
        provider = "groq"
        model = "test-model"
        latency_ms = 100.0
        input_tokens = 10
        output_tokens = 5

    telemetry = LLMTelemetry()

    telemetry.record(
        Response(),
        "first",
    )

    start = len(telemetry.calls)

    telemetry.record(
        Response(),
        "second",
    )

    records = telemetry.records_since(
        start
    )

    assert len(records) == 1
    assert records[0].purpose == "second"
        
def test_task_manager_can_pause_task():
    from advi.core.task_manager import TaskManager
    from advi.core.task import TaskStatus

    manager = TaskManager()

    task = manager.create(
        ["send_email"]
    )

    manager.start(task.task_id)
    manager.pause(task.task_id)

    assert (
        task.status
        == TaskStatus.PAUSED
    )        

def test_task_manager_can_resume_paused_task():
    from advi.core.task_manager import TaskManager
    from advi.core.task import TaskStatus

    manager = TaskManager()

    task = manager.create(
        ["send_email"]
    )

    manager.start(task.task_id)
    manager.pause(task.task_id)
    manager.resume(task.task_id)

    assert (
        task.status
        == TaskStatus.RUNNING
    )

def test_task_manager_can_await_confirmation():
    from advi.core.task_manager import TaskManager
    from advi.core.task import (
        TaskStatus,
        ConfirmationStatus,
    )

    manager = TaskManager()

    task = manager.create(
        ["send_email"]
    )

    manager.start(task.task_id)

    manager.await_confirmation(
        task.task_id,
        action="send_email",
        summary=(
            "Send the prepared email to David."
        ),
    )

    assert (
        task.status
        == TaskStatus.AWAITING_CONFIRMATION
    )

    assert task.confirmation is not None

    assert (
        task.confirmation.status
        == ConfirmationStatus.PENDING
    )

    assert (
        task.confirmation.action
        == "send_email"
    )

def test_task_manager_can_approve_confirmation():
    from advi.core.task_manager import TaskManager
    from advi.core.task import TaskStatus

    manager = TaskManager()

    task = manager.create(
        ["send_email"]
    )

    manager.start(task.task_id)

    manager.await_confirmation(
        task.task_id,
        action="send_email",
        summary="Send email to David.",
    )

    manager.approve(
        task.task_id
    )

    assert (
        task.status
        == TaskStatus.RUNNING
    )

    assert task.confirmation is None

def test_task_manager_rejects_confirmation():
    from advi.core.task_manager import TaskManager
    from advi.core.task import TaskStatus

    manager = TaskManager()

    task = manager.create(
        ["send_email"]
    )

    manager.start(task.task_id)

    manager.await_confirmation(
        task.task_id,
        action="send_email",
        summary="Send email to David.",
    )

    manager.reject(
        task.task_id
    )

    assert (
        task.status
        == TaskStatus.CANCELLED
    )

    assert task.confirmation is None       

def test_task_manager_tracks_current_step():
    from advi.core.task_manager import TaskManager

    manager = TaskManager()

    task = manager.create(
        [
            "draft_email",
            "send_email",
        ]
    )

    manager.start(task.task_id)

    manager.start_step(
        task.task_id,
        1,
    )

    assert task.current_step == 1 

def test_intent_detector_parses_task_confirmation():
    from advi.core.intent import IntentType
    from advi.core.intent_detector import IntentDetector

    class FakeProvider:
        def chat(self, messages):
            class Result:
                text = """
                {
                    "intent": "task_confirmation",
                    "confidence": 0.98,
                    "target": null,
                    "entities": {},
                    "parameters": {}
                }
                """

            return Result()

    result = IntentDetector(
        FakeProvider()
    ).detect("Yes, send it.")

    assert (
        result.type
        == IntentType.TASK_CONFIRMATION
    )
    assert result.confidence == 0.98

def test_intent_detector_parses_task_modification():
    from advi.core.intent import IntentType
    from advi.core.intent_detector import IntentDetector

    class FakeProvider:
        def chat(self, messages):
            class Result:
                text = """
                {
                    "intent": "task_modification",
                    "confidence": 0.96,
                    "target": "recipient",
                    "entities": {
                        "field": "recipient",
                        "value": "Daniel"
                    },
                    "parameters": {}
                }
                """

            return Result()

    result = IntentDetector(
        FakeProvider()
    ).detect(
        "Actually change the recipient to Daniel."
    )

    assert (
        result.type
        == IntentType.TASK_MODIFICATION
    )
    assert result.target == "recipient"
    assert (
        result.entities["value"]
        == "Daniel"
    )

def test_intent_detector_parses_task_resume():
    from advi.core.intent import IntentType
    from advi.core.intent_detector import IntentDetector

    class FakeProvider:
        def chat(self, messages):
            class Result:
                text = """
                {
                    "intent": "task_resume",
                    "confidence": 0.97,
                    "target": null,
                    "entities": {},
                    "parameters": {}
                }
                """

            return Result()

    result = IntentDetector(
        FakeProvider()
    ).detect(
        "Resume the email."
    )

    assert (
        result.type
        == IntentType.TASK_RESUME
    )    

def test_intent_detector_uses_current_task_context():
    from advi.core.intent import IntentType
    from advi.core.intent_detector import IntentDetector
    from advi.core.task import (
        Task,
        TaskStatus,
        ConfirmationRequest,
    )

    class FakeProvider:
        def __init__(self):
            self.messages = None

        def chat(self, messages):
            self.messages = messages

            class Result:
                text = """
                {
                    "intent": "task_confirmation",
                    "confidence": 0.99,
                    "target": null,
                    "entities": {},
                    "parameters": {}
                }
                """

            return Result()

    provider = FakeProvider()

    detector = IntentDetector(
        provider
    )

    task = Task(
        task_id="task-123",
        status=TaskStatus.AWAITING_CONFIRMATION,
        confirmation=ConfirmationRequest(
            action="send_email",
            summary="Send email to David.",
        ),
    )

    detector.set_current_task(
        task
    )

    result = detector.detect(
        "Yes, send it."
    )

    assert (
        result.type
        == IntentType.TASK_CONFIRMATION
    )

    assert provider.messages is not None

    prompt = provider.messages[1]["content"]

    assert "send_email" in prompt
    assert "Send email to David." in prompt
    assert "awaiting_confirmation" in prompt    


def test_task_coordinator_handles_confirmation():
    from advi.core.task_coordinator import TaskCoordinator
    from advi.core.intent import Intent, IntentType
    from advi.core.task import TaskStatus

    coordinator = TaskCoordinator()

    task = coordinator.task_manager.create(
        ["send_email"]
    )

    coordinator.task_manager.start(
        task.task_id
    )

    coordinator.task_manager.await_confirmation(
        task.task_id,
        action="send_email",
        summary="Send email to David.",
    )

    intent = Intent(
        type=IntentType.TASK_CONFIRMATION,
        confidence=0.99,
        original_input="Yes, send it.",
    )

    result = coordinator.handle_task_intent(
        intent
    )

    assert result is not None
    assert result.status == TaskStatus.RUNNING

def test_task_coordinator_handles_pause():
    from advi.core.task_coordinator import TaskCoordinator
    from advi.core.intent import Intent, IntentType
    from advi.core.task import TaskStatus

    coordinator = TaskCoordinator()

    task = coordinator.task_manager.create(
        ["send_email"]
    )

    coordinator.task_manager.start(
        task.task_id
    )

    intent = Intent(
        type=IntentType.TASK_PAUSE,
        confidence=0.98,
        original_input="Pause this.",
    )

    result = coordinator.handle_task_intent(
        intent
    )

    assert result is not None
    assert result.status == TaskStatus.PAUSED  

def test_task_coordinator_returns_none_without_current_task():
    from advi.core.task_coordinator import TaskCoordinator
    from advi.core.intent import Intent, IntentType

    coordinator = TaskCoordinator()

    intent = Intent(
        type=IntentType.TASK_CONFIRMATION,
        confidence=0.99,
        original_input="Yes.",
    )

    result = coordinator.handle_task_intent(
        intent
    )

    assert result is None  

def test_task_coordinator_handles_rejection():
    from advi.core.task_coordinator import TaskCoordinator
    from advi.core.intent import Intent, IntentType
    from advi.core.task import TaskStatus

    coordinator = TaskCoordinator()

    task = coordinator.task_manager.create(
        ["send_email"]
    )

    coordinator.task_manager.start(
        task.task_id
    )

    coordinator.task_manager.await_confirmation(
        task.task_id,
        action="send_email",
        summary="Send email to David.",
    )

    intent = Intent(
        type=IntentType.TASK_REJECTION,
        confidence=0.99,
        original_input="No, don't send it.",
    )

    result = coordinator.handle_task_intent(
        intent
    )

    assert result is not None
    assert result.status == TaskStatus.CANCELLED

def test_task_coordinator_handles_resume():
    from advi.core.task_coordinator import TaskCoordinator
    from advi.core.intent import Intent, IntentType
    from advi.core.task import TaskStatus

    coordinator = TaskCoordinator()

    task = coordinator.task_manager.create(
        ["send_email"]
    )

    coordinator.task_manager.start(
        task.task_id
    )

    coordinator.task_manager.pause(
        task.task_id
    )

    intent = Intent(
        type=IntentType.TASK_RESUME,
        confidence=0.99,
        original_input="Resume it.",
    )

    result = coordinator.handle_task_intent(
        intent
    )

    assert result is not None
    assert result.status == TaskStatus.RUNNING

def test_task_manager_updates_task_context():
    from advi.core.task_manager import TaskManager

    manager = TaskManager()

    task = manager.create(
        ["send_email"]
    )

    manager.update_context(
        task.task_id,
        {
            "recipient": "Daniel",
            "subject": "Project update",
        },
    )

    assert (
        task.context["recipient"]
        == "Daniel"
    )

    assert (
        task.context["subject"]
        == "Project update"
    )

def test_task_coordinator_handles_task_modification():
    from advi.core.task_coordinator import TaskCoordinator
    from advi.core.intent import Intent, IntentType

    coordinator = TaskCoordinator()

    task = coordinator.task_manager.create(
        ["send_email"]
    )

    coordinator.task_manager.update_context(
        task.task_id,
        {
            "recipient": "David",
        },
    )

    intent = Intent(
        type=IntentType.TASK_MODIFICATION,
        confidence=0.98,
        original_input=(
            "Change the recipient to Daniel."
        ),
        target="recipient",
        entities={
            "value": "Daniel",
        },
    )

    result = (
        coordinator.handle_task_intent(
            intent
        )
    )

    assert result is not None

    assert (
        result.context["recipient"]
        == "Daniel"
    )

def test_task_manager_can_pause_current_task():
    from advi.core.task_manager import TaskManager
    from advi.core.task import TaskStatus

    manager = TaskManager()

    task = manager.create(
        ["send_email"]
    )

    manager.start(task.task_id)

    paused = manager.pause_current()

    assert paused is task
    assert task.status == TaskStatus.PAUSED
    assert manager.current_task() is None

    assert task in manager.paused_tasks()

def test_task_manager_can_resume_last_paused_task():
    from advi.core.task_manager import TaskManager
    from advi.core.task import TaskStatus

    manager = TaskManager()

    task = manager.create(
        ["send_email"]
    )

    manager.start(task.task_id)
    manager.pause_current()

    resumed = manager.resume_last_paused()

    assert resumed is task
    assert task.status == TaskStatus.RUNNING
    assert manager.current_task() is task
    assert manager.paused_tasks() == []

def test_task_manager_resumes_most_recent_paused_task():
    from advi.core.task_manager import TaskManager

    manager = TaskManager()

    first = manager.create(
        ["email"]
    )

    manager.start(first.task_id)
    manager.pause_current()

    second = manager.create(
        ["calendar"]
    )

    manager.start(second.task_id)
    manager.pause_current()

    resumed = manager.resume_last_paused()

    assert resumed is second

def test_task_manager_pauses_previous_task_for_unrelated_work():
    from advi.core.task_manager import TaskManager
    from advi.core.task import TaskStatus

    manager = TaskManager()

    task = manager.create(
        ["send_email"]
    )

    manager.start(task.task_id)

    paused = manager.pause_current()

    assert paused is task
    assert task.status == TaskStatus.PAUSED
    assert manager.current_task() is None

    resumed = manager.resume_last_paused()

    assert resumed is task
    assert task.status == TaskStatus.RUNNING
    assert manager.current_task() is task

def test_task_coordinator_returns_current_task_context():
    from advi.core.task_coordinator import TaskCoordinator

    coordinator = TaskCoordinator()

    task = coordinator.task_manager.create(
        ["send_email"]
    )

    coordinator.task_manager.update_context(
        task.task_id,
        {
            "recipient": "David",
            "subject": "Project update",
            "body": "The project is ready.",
        },
    )

    context = (
        coordinator.get_current_task_context()
    )

    assert context == {
        "recipient": "David",
        "subject": "Project update",
        "body": "The project is ready.",
    }    

def test_task_readback_does_not_change_task_state():
    from advi.core.task_coordinator import TaskCoordinator
    from advi.core.intent import Intent, IntentType
    from advi.core.task import TaskStatus

    coordinator = TaskCoordinator()

    task = coordinator.task_manager.create(
        ["send_email"]
    )

    coordinator.task_manager.start(
        task.task_id
    )

    coordinator.task_manager.update_context(
        task.task_id,
        {
            "recipient": "David",
            "body": "The project is ready.",
        },
    )

    intent = Intent(
        type=IntentType.TASK_READBACK,
        confidence=0.99,
        original_input="Read it again.",
    )

    before = task.status

    result = coordinator.handle_task_intent(
        intent
    )

    assert result is None
    assert task.status == before
    assert task.context["recipient"] == "David"

def test_task_modification_invalidates_confirmation():
    from advi.core.task_manager import TaskManager
    from advi.core.task import TaskStatus

    manager = TaskManager()

    task = manager.create(
        ["send_email"]
    )

    manager.start(task.task_id)

    manager.update_context(
        task.task_id,
        {
            "recipient": "David",
        },
    )

    manager.await_confirmation(
        task.task_id,
        action="send_email",
        summary="Send email to David.",
    )

    assert task.confirmation is not None
    assert (
        task.status
        == TaskStatus.AWAITING_CONFIRMATION
    )

    manager.update_context(
        task.task_id,
        {
            "recipient": "Daniel",
        },
    )

    assert task.confirmation is None


def test_unchanged_task_context_keeps_confirmation():
    from advi.core.task_manager import TaskManager

    manager = TaskManager()

    task = manager.create(
        ["send_email"]
    )

    manager.update_context(
        task.task_id,
        {
            "recipient": "David",
        },
    )

    manager.start(task.task_id)

    manager.await_confirmation(
        task.task_id,
        action="send_email",
        summary="Send email to David.",
    )

    manager.update_context(
        task.task_id,
        {
            "recipient": "David",
        },
    )

    assert task.confirmation is not None    


def test_task_manager_full_focus_14_lifecycle():
    from advi.core.task_manager import TaskManager
    from advi.core.task import TaskStatus

    manager = TaskManager()

    # 1. Create task
    task = manager.create(
        ["draft_email", "send_email"]
    )

    manager.start(task.task_id)

    # 2. Add initial task data
    manager.update_context(
        task.task_id,
        {
            "recipient": "David",
            "subject": "Project update",
            "body": "The project is ready.",
        },
    )

    # 3. Modify task
    manager.update_context(
        task.task_id,
        {
            "recipient": "Daniel",
        },
    )

    assert (
        task.context["recipient"]
        == "Daniel"
    )

    # 4. Await confirmation
    manager.await_confirmation(
        task.task_id,
        action="send_email",
        summary="Send the project update to Daniel.",
    )

    assert (
        task.status
        == TaskStatus.AWAITING_CONFIRMATION
    )

    assert task.confirmation is not None

    # 5. Pause while awaiting confirmation
    manager.pause_current()

    assert (
        task.status
        == TaskStatus.PAUSED
    )

    assert manager.current_task() is None

    # 6. Resume
    resumed = manager.resume_last_paused()

    assert resumed is task
    assert (
        task.status
        == TaskStatus.RUNNING
    )

    # 7. Modification invalidates old confirmation
    manager.await_confirmation(
        task.task_id,
        action="send_email",
        summary="Send the project update to Daniel.",
    )

    assert task.confirmation is not None

    manager.update_context(
        task.task_id,
        {
            "subject": "Final project update",
        },
    )

    assert task.confirmation is None

    # 8. Ask for confirmation again
    manager.await_confirmation(
        task.task_id,
        action="send_email",
        summary="Send the final project update to Daniel.",
    )

    assert (
        task.status
        == TaskStatus.AWAITING_CONFIRMATION
    )

    # 9. Approve
    approved = manager.approve(
        task.task_id
    )

    assert approved is task
    assert (
        task.status
        == TaskStatus.RUNNING
    )
    assert task.confirmation is None

    # 10. Complete both steps
    manager.start_step(
        task.task_id,
        0,
    )

    manager.complete_step(
        task.task_id,
        0,
        "Draft created.",
    )

    manager.start_step(
        task.task_id,
        1,
    )

    manager.complete_step(
        task.task_id,
        1,
        "Email sent.",
    )

    assert (
        task.status
        == TaskStatus.COMPLETED
    )


def test_executor_creates_email_draft():
    from advi.core.executor import Executor
    from advi.core.planner import PlanStep

    class FakeGmail:
        def create_draft(
            self,
            to,
            subject,
            body,
        ):
            from types import SimpleNamespace

            return SimpleNamespace(
                draft_id="draft-1",
                recipient=to,
                subject=subject,
                body=body,
            )

    executor = Executor(
        gmail_service=FakeGmail()
    )

    step = PlanStep(
        action="email_draft_create",
        parameters={
            "recipient": "david@example.com",
            "subject": "Project update",
            "body": "The project is ready.",
        },
        original_input=(
            "Send David an email."
        ),
    )

    result = executor.execute(step)

    assert result.success is True
    assert result.data.draft_id == "draft-1"
    assert (
        result.data.recipient
        == "david@example.com"
    )

def test_executor_rejects_email_draft_without_required_fields():
    from advi.core.executor import Executor
    from advi.core.planner import PlanStep

    class FakeGmail:
        def create_draft(
            self,
            to,
            subject,
            body,
        ):
            raise AssertionError(
                "Gmail should not be called."
            )

    executor = Executor(
        gmail_service=FakeGmail()
    )

    step = PlanStep(
        action="email_draft_create",
        parameters={
            "recipient": "david@example.com",
        },
    )

    result = executor.execute(step)

    assert result.success is False
    assert (
        "requires"
        in result.error
    )

def test_executor_updates_email_draft():
    from advi.core.executor import Executor
    from advi.core.planner import PlanStep

    class FakeGmail:
        def update_draft(
            self,
            draft_id,
            to,
            subject,
            body,
        ):
            return {
                "draft_id": draft_id,
                "recipient": to,
                "subject": subject,
                "body": body,
            }

    executor = Executor(
        gmail_service=FakeGmail()
    )

    step = PlanStep(
        action="email_draft_update",
        parameters={
            "draft_id": "draft-1",
            "recipient": "daniel@example.com",
            "subject": "Updated",
            "body": "Updated body.",
        },
    )

    result = executor.execute(step)

    assert result.success is True
    assert result.data["draft_id"] == "draft-1"

def test_executor_reads_email_draft():
    from advi.core.executor import Executor
    from advi.core.planner import PlanStep

    class FakeGmail:
        def get_draft(
            self,
            draft_id,
        ):
            return {
                "draft_id": draft_id,
                "subject": "Project update",
            }

    executor = Executor(
        gmail_service=FakeGmail()
    )

    step = PlanStep(
        action="email_draft_read",
        parameters={
            "draft_id": "draft-1",
        },
    )

    result = executor.execute(step)

    assert result.success is True
    assert result.data["draft_id"] == "draft-1"


def test_capability_prompt_reports_email_availability():
    from advi.core.capabilities import (
        capability_for_prompt,
    )

    unavailable = capability_for_prompt(
        email_available=False
    )

    available = capability_for_prompt(
        email_available=True
    )

    assert "Email/Gmail: unavailable" in unavailable
    assert "Email/Gmail: available" in available


def test_intent_detector_parses_email_draft_create():
    from advi.core.intent import (
        IntentType,
    )
    from advi.core.intent_detector import (
        IntentDetector,
    )

    class FakeProvider:
        def chat(self, messages):
            class Result:
                text = """
                {
                    "intent": "email_draft_create",
                    "confidence": 0.98,
                    "target": null,
                    "entities": {
                        "recipient": "david@example.com",
                        "subject": "Project Update",
                        "body": "The project is ready."
                    },
                    "parameters": {}
                }
                """

            return Result()

    result = IntentDetector(
        FakeProvider()
    ).detect(
        "Draft an email to david@example.com saying the project is ready."
    )

    assert (
        result.type
        == IntentType.EMAIL_DRAFT_CREATE
    )

    assert (
        result.entities["recipient"]
        == "david@example.com"
    )

    assert (
        result.entities["subject"]
        == "Project Update"
    )

    assert (
        result.entities["body"]
        == "The project is ready."
    )

def test_planner_creates_email_draft_plan():
    from advi.core.intent import (
        Intent,
        IntentType,
    )
    from advi.core.planner import Planner

    intent = Intent(
        type=IntentType.EMAIL_DRAFT_CREATE,
        confidence=0.98,
        original_input=(
            "Draft an email to david@example.com "
            "saying the project is ready."
        ),
        entities={
            "recipient": "david@example.com",
            "subject": "Project Update",
            "body": "The project is ready.",
        },
    )

    plan = Planner().create_plan(intent)

    assert plan.status.value == "ready"
    assert len(plan.steps) == 1

    step = plan.steps[0]

    assert step.action == "email_draft_create"
    assert (
        step.parameters["recipient"]
        == "david@example.com"
    )
    assert (
        step.parameters["subject"]
        == "Project Update"
    )
    assert (
        step.parameters["body"]
        == "The project is ready."
    )

def test_email_draft_waits_for_confirmation():
    from advi.core.task_manager import (
        TaskManager,
    )
    from advi.core.task import (
        TaskStatus,
    )

    manager = TaskManager()

    task = manager.create(
        ["email_draft_create"]
    )

    manager.start(task.task_id)

    manager.start_step(
        task.task_id,
        0,
    )

    manager.await_confirmation(
        task.task_id,
        action="email_send",
        summary=(
            "Email to david@example.com; "
            "subject: Project Update"
        ),
    )

    manager.complete_step(
        task.task_id,
        0,
        result="draft-1",
    )

    current = manager.get(
        task.task_id
    )

    assert current is not None

    assert (
        current.status
        == TaskStatus.AWAITING_CONFIRMATION
    )

    assert (
        current.confirmation is not None
    )

    assert (
        current.confirmation.action
        == "email_send"
    )    

def test_task_coordinator_reads_current_gmail_draft():
    from advi.core.task_coordinator import (
        TaskCoordinator,
    )
    from advi.core.task_manager import TaskManager

    class FakeGmail:
        def get_draft(self, draft_id):
            from types import SimpleNamespace

            assert draft_id == "draft-1"

            return SimpleNamespace(
                draft_id="draft-1",
                recipient="david@example.com",
                subject="Project Update",
                body="The project is ready.",
            )

    class FakeExecutor:
        def __init__(self):
            self.gmail_service = FakeGmail()

        def execute(self, step):
            return ExecutionResult(
                action=step.action,
                success=True,
                data=self.gmail_service.send_draft(
                    step.parameters["draft_id"]
                ),
            )

    manager = TaskManager()

    coordinator = TaskCoordinator(
        executor=FakeExecutor(),
        task_manager=manager,
    )

    task = manager.create(
        ["email_draft_create"]
    )

    manager.update_context(
        task.task_id,
        {
            "gmail_draft_id": "draft-1",
        },
    )

    draft = coordinator.readback_current_task()

    assert draft is not None
    
    assert draft.draft_id == "draft-1"
    assert draft.recipient == (
        "david@example.com"
    )
    assert draft.subject == (
        "Project Update"
    )    

def test_task_coordinator_updates_existing_gmail_draft():
    from advi.core.task_coordinator import (
        TaskCoordinator,
    )
    from advi.core.task_manager import (
        TaskManager,
    )
    from types import SimpleNamespace

    class FakeGmail:
        def update_draft(
            self,
            draft_id,
            to,
            subject,
            body,
        ):
            assert draft_id == "draft-1"

            return SimpleNamespace(
                draft_id=draft_id,
                recipient=to,
                subject=subject,
                body=body,
            )

    class FakeExecutor:
        def __init__(self):
            self.gmail_service = FakeGmail()

        def execute(self, step):
            from advi.core.executor import ExecutionResult

            result = self.gmail_service.send_draft(
                step.parameters["draft_id"]
            )

            return ExecutionResult(
                action=step.action,
                success=True,
                data=result,
            )

    manager = TaskManager()

    coordinator = TaskCoordinator(
        executor=FakeExecutor(),
        task_manager=manager,
    )

    task = manager.create(
        ["email_draft_create"]
    )

    manager.update_context(
        task.task_id,
        {
            "gmail_draft_id": "draft-1",
            "email_recipient": (
                "david@example.com"
            ),
            "email_subject": "Old subject",
            "email_body": "Original body.",
        },
    )

    updated = coordinator.modify_current_task(
        {
            "email_subject": "New subject",
        }
    )

    assert updated is not None
    assert updated.draft_id == "draft-1"
    assert updated.recipient == (
        "david@example.com"
    )
    assert updated.subject == "New subject"
    assert updated.body == "Original body."

    context = (
        coordinator.get_current_task_context()
    )

    assert (
        context["email_subject"]
        == "New subject"
    )    


def test_email_confirmation_routes_through_executor():
    from advi.core.executor import ExecutionResult
    from advi.core.intent import Intent, IntentType
    from advi.core.task_coordinator import TaskCoordinator
    from advi.core.task_manager import TaskManager

    class FakeGmail:
        def __init__(self):
            self.sent_draft_id = None

        def send_draft(self, draft_id):
            self.sent_draft_id = draft_id

            return {
                "id": "sent-message-1",
                "threadId": "thread-1",
            }

    class FakeExecutor:
        def __init__(self):
            self.gmail_service = FakeGmail()
            self.executed_step = None

        def execute(self, step):
            self.executed_step = step

            result = self.gmail_service.send_draft(
                step.parameters["draft_id"]
            )

            return ExecutionResult(
                action=step.action,
                success=True,
                data=result,
            )

    manager = TaskManager()
    executor = FakeExecutor()

    coordinator = TaskCoordinator(
        executor=executor,
        task_manager=manager,
    )

    task = manager.create(
        ["email_draft_create"]
    )

    manager.start(task.task_id)

    manager.update_context(
        task.task_id,
        {
            "gmail_draft_id": "draft-1",
        },
    )

    manager.await_confirmation(
        task.task_id,
        action="email_send",
        summary="Send email",
    )

    result = coordinator.handle_task_intent(
        Intent(
            type=IntentType.TASK_CONFIRMATION,
            confidence=0.99,
            original_input="yes",
        )
    )

    assert result is not None
    assert result.success is True
    assert result.action == "email_send"
    assert result.data["id"] == "sent-message-1"

    assert executor.executed_step is not None
    assert executor.executed_step.action == "email_send"
    assert (
        executor.executed_step.parameters["draft_id"]
        == "draft-1"
    )

    assert (
        executor.gmail_service.sent_draft_id
        == "draft-1"
    )

def test_email_recipient_uses_structured_contact_lookup():
    from pathlib import Path

    from advi.core.executor import Executor
    from advi.core.task_coordinator import TaskCoordinator
    from advi.memory.long_term import LongTermMemory

    memory = LongTermMemory(
        Path("runtime/memory/test_contacts.db")
    )

    memory.save_contact(
        "Joel",
        "joelpaulson105@gmail.com",
    )

    executor = Executor(
        memory=memory,
    )

    coordinator = TaskCoordinator(
        executor=executor,
    )

    assert (
        coordinator.resolve_email_recipient("Joel")
        == "joelpaulson105@gmail.com"
    )          





def test_failed_execution_is_marked_for_final_response():
    from advi.core.conversation import ConversationEngine
    from advi.core.executor import ExecutionResult

    engine = ConversationEngine(
        provider=None,
    )

    result = ExecutionResult(
        action="email_draft_create",
        success=False,
        error="Invalid To header",
    )

    failed_actions = [
        item
        for item in [result]
        if not item.success
    ]

    assert len(failed_actions) == 1
    assert failed_actions[0].action == "email_draft_create"
    assert failed_actions[0].error == "Invalid To header"    
