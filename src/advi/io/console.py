from __future__ import annotations


def print_banner() -> None:
    print("╭──────────────────────────────────────────────────────────────╮")
    print("│ ADVI — Autonomous Desktop for Visually Impaired              │")
    print("│ Runtime online                                                │")
    print("╰──────────────────────────────────────────────────────────────╯")


def read_line() -> str:
    return input("\nYou › ").strip()


def print_shutdown() -> None:
    print("\nADVI › Shutting down.")
