from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Ensure local src directory is prioritized in sys.path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from advi.fallback.execution_loop import ExecutionLoop
from advi.fallback.intent_service import IntentService
from advi.fallback.planner_service import PlannerService
from advi.providers import GroqProvider

MODEL = "openai/gpt-oss-safeguard-20b"


def main() -> None:
    load_dotenv()

    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not configured."
        )

    provider = GroqProvider(
        api_key=api_key,
        model=MODEL,
    )

    prompt_path = (
        Path(__file__).parent
        / "src"
        / "advi"
        / "fallback"
        / "prompts"
    )

    intent_service = IntentService(
        provider=provider,
        prompt_path=(
            prompt_path
            / "intent_prompt.txt"
        ),
    )

    planner_service = PlannerService(
        provider=provider,
        prompt_path=(
            prompt_path
            / "planner_prompt.txt"
        ),
    )

    execution_loop = ExecutionLoop()

    print("=" * 60)
    print("ADVI FALLBACK FULL PIPELINE TEST")
    print("=" * 60)

    user_input = input(
        "\nEnter your request: "
    ).strip()

    if not user_input:
        print("No input provided.")
        return

    conversation = [
        f"User: {user_input}"
    ]

    # --------------------------------------------------
    # INTENT LOOP
    # --------------------------------------------------

    while True:
        current_input = "\n".join(
            conversation
        )

        print(
            "\n[1] GENERATING INTENT..."
        )

        intent = intent_service.extract_intent(
            current_input
        )

        print("\nINTENT:")
        print(
            intent.model_dump_json(
                indent=2
            )
        )

        # --------------------------------------------------
        # Missing information
        # --------------------------------------------------

        if intent.missing_information:
            print(
                "\nADVI needs more information:"
            )

            for item in (
                intent.missing_information
            ):
                print(
                    f"- {item}"
                )

            answer = input(
                "\nYour answer: "
            ).strip()

            if not answer:
                print(
                    "No answer provided."
                )
                continue

            conversation.append(
                f"ADVI: I need: "
                f"{', '.join(intent.missing_information)}"
            )

            conversation.append(
                f"User: {answer}"
            )

            continue

        # --------------------------------------------------
        # Confirmation
        # --------------------------------------------------

        if intent.confirmation_required:
            print(
                "\nThis action requires confirmation."
            )

            answer = input(
                "Proceed? (yes/no): "
            ).strip().lower()

            if answer not in {
                "yes",
                "y",
            }:
                print(
                    "\nTask cancelled."
                )
                return

            conversation.append(
                f"User confirmation: {answer}"
            )

            continue

        break

    # --------------------------------------------------
    # ACTION PLAN
    # --------------------------------------------------

    print(
        "\n[2] GENERATING ACTION PLAN..."
    )

    plan = planner_service.generate_plan(
        intent
    )

    print("\nACTION PLAN:")
    print(
        plan.model_dump_json(
            indent=2
        )
    )

    if not plan.actions:
        print(
            "\nPlanner returned no actions."
        )
        return

    # --------------------------------------------------
    # EXECUTION
    # --------------------------------------------------

    print(
        "\n[3] STARTING EXECUTION LOOP..."
    )

    result = execution_loop.run(
        plan
    )

    # --------------------------------------------------
    # RESULTS
    # --------------------------------------------------

    print(
        "\n[4] EXECUTION RESULT"
    )

    print(
        f"Overall success: "
        f"{result.success}"
    )

    for index, item in enumerate(
        result.results,
        start=1,
    ):
        print(
            f"\nAction #{index}"
        )

        print(
            f"  action: {item.action}"
        )

        print(
            f"  success: {item.success}"
        )

        print(
            f"  data: {item.data}"
        )

        print(
            f"  error: {item.error}"
        )

    print(
        "\n" + "=" * 60
    )
    print(
        "TEST COMPLETE"
    )
    print(
        "=" * 60
    )


if __name__ == "__main__":
    main()