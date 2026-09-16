from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CapabilityStatus(str, Enum):
    """Current operational status of an ADVI capability."""

    AVAILABLE = "available"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class Capability:
    """Description of one capability known to ADVI."""

    name: str
    description: str
    status: CapabilityStatus


CAPABILITIES: dict[str, Capability] = {
    "conversation": Capability(
        name="conversation",
        description=(
            "Understand and respond to natural-language conversation."
        ),
        status=CapabilityStatus.AVAILABLE,
    ),
    "memory": Capability(
        name="memory",
        description=(
            "Remember and retrieve durable user information."
        ),
        status=CapabilityStatus.AVAILABLE,
    ),
    "session_continuity": Capability(
        name="session_continuity",
        description=(
            "Use useful context from previous sessions."
        ),
        status=CapabilityStatus.AVAILABLE,
    ),
    "speech_output": Capability(
        name="speech_output",
        description=(
            "Speak responses using Piper text-to-speech."
        ),
        status=CapabilityStatus.AVAILABLE,
    ),
    "email": Capability(
        name="email",
        description=(
            "Read, search, draft, modify, and send email "
            "through the connected Gmail account."
        ),
        status=CapabilityStatus.UNAVAILABLE,
    ),
    "web_search": Capability(
        name="web_search",
        description=(
            "Search the internet and navigate web pages via Chrome CDP."
        ),
        status=CapabilityStatus.UNAVAILABLE,
    ),
    "vision": Capability(
        name="vision",
        description=(
            "Understand visual information from the computer screen."
        ),
        status=CapabilityStatus.UNAVAILABLE,
    ),
    "desktop_control": Capability(
        name="desktop_control",
        description=(
            "Control desktop applications, keyboard, mouse, and system functions."
        ),
        status=CapabilityStatus.UNAVAILABLE,
    ),
}


def set_capability_status(
    name: str,
    status: CapabilityStatus,
) -> None:
    """Dynamically update capability status at runtime."""
    key = name.strip().lower()
    if key in CAPABILITIES:
        cap = CAPABILITIES[key]
        CAPABILITIES[key] = Capability(
            name=cap.name,
            description=cap.description,
            status=status,
        )


def get_capability(
    name: str,
) -> Capability | None:
    """Return a capability by name."""

    return CAPABILITIES.get(
        name.strip().lower()
    )


def available_capabilities() -> list[Capability]:
    """Return capabilities that ADVI can currently use."""

    return [
        capability
        for capability in CAPABILITIES.values()
        if capability.status
        != CapabilityStatus.UNAVAILABLE
    ]


def unavailable_capabilities() -> list[Capability]:
    """Return capabilities that ADVI cannot currently use."""

    return [
        capability
        for capability in CAPABILITIES.values()
        if capability.status
        == CapabilityStatus.UNAVAILABLE
    ]


def capability_summary() -> str:
    """
    Produce a compact human-readable capability summary.

    This is intended for future model/planner context,
    not for direct user output.
    """

    available = available_capabilities()
    unavailable = unavailable_capabilities()

    lines = [
        "Available capabilities:"
    ]

    for capability in available:
        lines.append(
            f"- {capability.name}: {capability.description}"
        )

    lines.append("")
    lines.append("Unavailable capabilities:")

    for capability in unavailable:
        lines.append(
            f"- {capability.name}: {capability.description}"
        )

    return "\n".join(lines)

def can_use(name: str) -> bool:
    """Return True only when a capability is currently available."""

    capability = get_capability(name)

    return (
        capability is not None
        and capability.status == CapabilityStatus.AVAILABLE
    )


def capability_for_prompt(
    email_available: bool = False,
) -> str:
    """
    Build compact capability context for the language model.

    Only capabilities that matter to self-awareness are exposed.
    """

    email_status = (
        "available"
        if email_available
        else "unavailable"
    )

    return (
        "ADVI capability state:\n"
        "- Conversation: available\n"
        "- Long-term memory: available\n"
        "- Session continuity: available\n"
        "- Speech output: available\n"
        f"- Email/Gmail: {email_status}\n"
        "- Web search: unavailable\n"
        "- Screen/vision understanding: unavailable\n"
        "- Desktop control: unavailable\n\n"
        "Never claim to have an unavailable capability."
    )

def capability_for_registry_prompt(registry: object) -> str:
    """Render self-awareness context from the authoritative runtime registry."""
    if registry is None or not hasattr(registry, "summary_for_prompt"):
        return capability_for_prompt()
    return "ADVI runtime capability state (authoritative):\n" + registry.summary_for_prompt() + (
        "\n\nNever claim to have an unavailable capability."
    )
