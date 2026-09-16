from __future__ import annotations

import logging

from advi.brain.agent import ADVIAgent
from advi.brain.fallback_gateway import DavidFallbackGateway
from advi.capabilities.registry import build_default_registry
from advi.core.execution_engine import ExecutionEngine
from advi.core.config import PROJECT_ROOT
from advi.core.runtime import Runtime
from advi.core.startup_health import StartupHealthValidator
from advi.core.verification import ActionVerifier
from advi.integrations.gmail import GmailService
from advi.fallback.service import FallbackService
from advi.io.console import (
    print_banner,
    print_shutdown,
    read_line,
)
from advi.io.output import (
    AdviResponse,
    OutputManager,
)
from advi.io.tts import PiperTTS
from advi.memory.consolidator import SessionConsolidator
from advi.memory.retriever import MemoryRetriever
from advi.memory.session import SessionBuffer
from advi.memory.short_term import ShortTermMemory
from advi.providers import (
    GeminiProvider,
    GroqProvider,
    ResilientLLMProvider,
)

logger = logging.getLogger(__name__)


def main() -> None:
    runtime = Runtime.create()
    runtime.start()

    print_banner()

    settings = runtime.settings

    tts = PiperTTS(
        executable=settings.piper_exe,
        model=settings.piper_model,
        output_wav=settings.tts_output,
    )

    output = OutputManager(
        tts=tts if tts.available() else None
    )
    runtime.register_resource(output)

    if not settings.groq_api_key and not settings.gemini_api_key:
        output.deliver(
            AdviResponse(
                "Neither Groq nor Gemini API key is configured. "
                "Conversation is currently unavailable."
            )
        )
        runtime.shutdown()
        print_shutdown()
        return

    provider = None
    if settings.groq_api_key:
        provider = GroqProvider(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
        )

    gemini_provider = None
    if settings.gemini_api_key:
        gemini_provider = GeminiProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
        )

    providers = [p for p in (gemini_provider, provider) if p is not None]
    active_provider = (
        ResilientLLMProvider(providers)
        if len(providers) > 1
        else providers[0]
    )
    runtime.register_resource(active_provider)

    retriever = MemoryRetriever(runtime.memory)

    previous_session_context = ""
    if runtime.memory is not None:
        sessions = runtime.memory.recent_sessions(limit=3)
        if sessions:
            previous_session_context = "\n".join(
                f"- {session['summary']}"
                for session in sessions
                if session.get("summary")
            )

    gmail_service = None
    try:
        gmail_service = GmailService()
        runtime.register_resource(gmail_service)
    except Exception as exc:
        logger.info("Gmail integration not available: %s", exc)

    # Build authoritative capability registry and execution engine
    registry = build_default_registry(
        memory=runtime.memory,
        retriever=retriever,
        gmail_service=gmail_service,
    )
    for capability in registry.capabilities.values():
        if capability.handler is not None:
            runtime.register_resource(capability.handler)

    execution_engine = ExecutionEngine(
        registry=registry,
        verifier=ActionVerifier(),
        execution_journal=runtime.execution_journal,
    )

    # Initialize unified cognitive brain
    # David remains a separate fallback agent. ADVI only reaches it through the
    # narrow gateway after the primary failure policy allows the hand-off.
    fallback_gateway = None
    try:
        fallback_service = FallbackService(
            provider=active_provider,
            intent_prompt_path=PROJECT_ROOT / "src" / "advi" / "fallback" / "prompts" / "intent_prompt.txt",
            planner_prompt_path=PROJECT_ROOT / "src" / "advi" / "fallback" / "prompts" / "planner_prompt.txt",
        )
        fallback_gateway = DavidFallbackGateway(fallback_service)
    except Exception:
        logger.exception("David fallback could not be initialized; ADVI will run without fallback.")

    agent = ADVIAgent(
        provider=active_provider,
        execution_engine=execution_engine,
        registry=registry,
        short_term_memory=ShortTermMemory(),
        session_buffer=SessionBuffer(),
        retriever=retriever,
        previous_session_context=previous_session_context,
        task_persistence=runtime.task_persistence,
        execution_journal=runtime.execution_journal,
        runtime=runtime,
        fallback_gateway=fallback_gateway,
    )

    consolidator = SessionConsolidator(active_provider)

    # Read-only startup gate. Degraded optional services do not prevent ADVI
    # from starting, while structurally unsafe runtime states do.
    startup = StartupHealthValidator().validate(agent.health(refresh_capabilities=True))
    if startup.state == "not_ready":
        logger.error("Startup health check blocked interactive mode: %s", startup.blocking_checks)
        output.deliver(AdviResponse(startup.message))
        runtime.shutdown()
        print_shutdown()
        return
    if startup.state == "degraded":
        logger.warning("ADVI starting in degraded mode: %s", startup.degraded_checks)

    try:
        while True:
            try:
                user_input = read_line()
            except EOFError:
                print()
                break
            except KeyboardInterrupt:
                print()
                break

            if not user_input:
                continue

            if user_input.lower() in {
                "exit",
                "quit",
                "stop",
                "sleep",
            }:
                break

            logger.info("User input received: %r", user_input)

            try:
                response = agent.respond(user_input)
                output.deliver(response)
            except Exception:
                logger.exception("Agent request failed.")
                output.deliver(
                    AdviResponse(
                        "I'm sorry, but I encountered an issue processing that request."
                    )
                )

    finally:
        _consolidate_session(
            agent=agent,
            consolidator=consolidator,
            runtime=runtime,
        )
        runtime.shutdown(session_summary=runtime.session_summary)
        print_shutdown()


def _consolidate_session(
    agent: ADVIAgent,
    consolidator: SessionConsolidator,
    runtime: Runtime,
) -> None:
    messages = agent.get_session_buffer()
    if not messages:
        return

    try:
        result = consolidator.consolidate(messages)
        runtime.session_summary = result.summary
        if runtime.memory is not None:
            runtime.memory.save_consolidation(result, session_id=runtime.session_id)
    except Exception:
        logger.exception("Session consolidation failed.")


if __name__ == "__main__":
    main()