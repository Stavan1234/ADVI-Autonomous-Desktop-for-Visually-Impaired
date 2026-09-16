from __future__ import annotations

import json
import logging
from pathlib import Path

from ..providers import LLMProvider
from .intent_schema import Intent


logger = logging.getLogger(__name__)


class IntentService:
    """Extract an agentic desktop intent from user input."""

    def __init__(
        self,
        provider: LLMProvider,
        prompt_path: str | Path,
    ) -> None:
        self.provider = provider

        prompt_file = Path(prompt_path)

        with prompt_file.open(
            "r",
            encoding="utf-8",
        ) as file:
            self.prompt = file.read()

    def extract_intent(
        self,
        user_input: str,
    ) -> Intent:
        full_prompt = (
            f"{self.prompt}\n\n"
            "User Input:\n\n"
            f"{user_input}"
        )

        result = self.provider.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "You are ADVI's agentic desktop "
                        "intent extraction component. "
                        "Return only valid JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": full_prompt,
                },
            ]
        )

        response = result.text.strip()

        intent_dict = json.loads(response)

        return Intent(
            **intent_dict
        )