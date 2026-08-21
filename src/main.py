"""Shadow — thin REPL with resilient Piper TTS wiring.

All of the intelligence lives in brain.Brain (tool schemas, conversation memory,
Groq orchestration, local Groq-free file-search short-circuits, path safety).
This file only reads a line of input, speaks the result back through Piper TTS,
and prints structured data (e.g. file-search matches) to the console.

TTS is optional: if the piper/sounddevice stack is unavailable or out.wav is
locked by another process, the loop keeps running in text-only mode instead of
crashing.
"""

import logging
import sys

from brain import Brain, CommandResult

# Safe import of local TTS module
try:
    from src import tts
    TTS_AVAILABLE = True
except ImportError:
    try:
        import tts
        TTS_AVAILABLE = True
    except ImportError:
        TTS_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def speak(text: str) -> None:
    """
    Prints response to console and triggers Piper TTS audio synthesis.
    Fails gracefully to text-only if the audio device or file is locked.
    """
    print(f"\nAssistant: {text}")

    if not TTS_AVAILABLE:
        logger.debug("TTS module not found; running in text-only mode.")
        return

    try:
        success = tts.speak(text)
        if not success:
            logger.warning("TTS synthesis or playback returned non-success status.")
    except Exception:
        # Catch subprocess errors, missing piper.exe, or locked out.wav
        logger.exception("TTS Engine failure. Continuing in text-only mode.")


def run_loop() -> None:
    assistant_brain = Brain()
    assistant_brain.start()  # builds the filesystem + installed-app indexes
    speak("System online. How can I help you?")

    while True:
        try:
            # Phase 1/2 Text Input (ready to swap for STT in Phase 3)
            user_input = input("\nYou: ").strip()

            if not user_input:
                continue

            if user_input.lower() in {"exit", "quit", "stop"}:
                speak("Shutting down. Goodbye!")
                break

            # Dispatch command to the new Intent-Planner-Executor Orchestrator
            try:
                from src.brain import run_shadow
            except ImportError:
                from brain import run_shadow

            run_shadow(user_input)

        except KeyboardInterrupt:
            speak("Force quit detected. Offline.")
            sys.exit(0)
        except EOFError:
            # stdin closed (e.g. piped input) — exit cleanly instead of looping
            print()
            break
        except Exception:
            logger.exception("Fatal loop error caught.")
            speak("A critical loop error occurred, but I am still listening.")


if __name__ == "__main__":
    run_loop()

