from __future__ import annotations


def format_memory_answer(
    user_input: str,
    value: str,
) -> str:
    text = user_input.lower()

    if "father" in text:
        return f"Your father's name is {value}."

    if "mother" in text:
        return f"Your mother's name is {value}."

    if "name" in text:
        return f"Your name is {value}."

    if "where do i study" in text:
        return f"You study at {value}."

    if "where are you studying" in text:
        return f"You study at {value}."

    return value


def format_identity_answer(
    user_input: str,
) -> str:
    text = user_input.lower()

    if (
        "who created you" in text
        or "who made you" in text
    ):
        return (
            "I don't have a confirmed record of who created me."
        )

    return (
        "I'm ADVI, the Autonomous Desktop for the Visually "
        "Impaired. I'm your voice-oriented desktop assistant."
    )


def format_capability_answer() -> str:
    return (
        "I can have conversations, remember relevant information "
        "about you, maintain session context, and speak responses. "
        "I currently cannot search the web, see your screen, "
        "or control your desktop."
    )