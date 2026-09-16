from __future__ import annotations

from typing import Any


def _line() -> None:
    print("─" * 48)


def show_section(title: str) -> None:
    print()
    _line()
    print(f" {title}")
    _line()


def show_intent(intent: Any) -> None:
    show_section("INTENT")

    print(f"Type       : {intent.type.value}")
    print(f"Confidence : {intent.confidence:.2f}")

    if intent.target:
        print(f"Target     : {intent.target}")

    if intent.entities:
        print(f"Entities   : {intent.entities}")


def show_plan(plan: Any) -> None:
    show_section("PLAN")

    print(f"Goal       : {plan.goal}")
    print(f"Status     : {plan.status.value}")
    print(f"Confidence : {plan.confidence:.2f}")
    print(f"Steps      : {len(plan.steps)}")

    for index, step in enumerate(
        plan.steps,
        start=1,
    ):
        print(f"  {index}. {step.action}")


def show_task(task: Any) -> None:
    show_section("TASK")

    print(f"ID         : {task.task_id}")
    print(f"Status     : {task.status.value}")

    if task.steps:
        print("Steps:")

        for index, step in enumerate(
            task.steps,
            start=1,
        ):
            symbol = {
                "pending": "○",
                "running": "→",
                "completed": "✓",
                "failed": "✗",
            }.get(
                step.status.value,
                "•",
            )

            print(
                f"  {symbol} {index}. "
                f"{step.action} "
                f"[{step.status.value}]"
            )

    if task.error:
        print(f"Error      : {task.error}")

def show_llm_summary(
        records: list[Any],
    ) -> None:
        if not records:
            return

        show_section("LLM SUMMARY")

        for index, record in enumerate(
            records,
            start=1,
        ):
            latency = (
                f"{record.latency_ms:.0f} ms"
                if record.latency_ms is not None
                else "n/a"
            )

            input_tokens = (
                record.input_tokens
                if record.input_tokens is not None
                else "?"
            )

            output_tokens = (
                record.output_tokens
                if record.output_tokens is not None
                else "?"
            )

            total_tokens = (
                record.total_tokens
                if record.total_tokens is not None
                else "?"
            )

            print(
                f"{index}. "
                f"{record.purpose:<20} "
                f"{record.provider:<8} "
                f"{latency:<10} "
                f"{input_tokens} in / "
                f"{output_tokens} out / "
                f"{total_tokens} total"
            )

        total_input = sum(
            record.input_tokens or 0
            for record in records
        )

        total_output = sum(
            record.output_tokens or 0
            for record in records
        )

        total_latency = sum(
            record.latency_ms or 0.0
            for record in records
        )

        print("─" * 48)
        print(f"Calls      : {len(records)}")
        print(f"Input      : {total_input}")
        print(f"Output     : {total_output}")
        print(f"Total      : {total_input + total_output}")
        print(f"Latency    : {total_latency:.0f} ms")       