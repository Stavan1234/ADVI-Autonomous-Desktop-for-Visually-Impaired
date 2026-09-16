from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable
from datetime import datetime, timezone
import os

from advi.core.action_contracts import get_action_contract




@dataclass(frozen=True)
class ActionSpec:
    """Canonical runtime view of one executable ADVI action.

    This is composed from the authoritative capability registry plus the
    canonical parameter contract. Consumers should use this object instead
    of rebuilding action semantics themselves.
    """

    action: str
    capability: str
    description: str
    side_effect: str
    requires_confirmation: bool
    verification: str
    parameters: dict[str, dict[str, Any]] = field(default_factory=dict)

    def required_parameters(self) -> list[str]:
        return [name for name, spec in self.parameters.items() if spec.get("required")]

    def to_prompt_line(self) -> str:
        return (
            f"- {self.action}: {self.description} | side_effect={self.side_effect} | "
            f"confirmation={str(self.requires_confirmation).lower()} | verification={self.verification} | "
            f"required_parameters={','.join(self.required_parameters()) or 'none'}"
        )


class CapabilityStatus(str, Enum):
    AVAILABLE = "available"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class AvailabilitySnapshot:
    """Runtime availability evidence for one capability."""

    capability: str
    status: CapabilityStatus
    reason: str
    checked_at: str


@dataclass
class Capability:
    """Definition of a concrete capability supported by ADVI."""
    name: str
    description: str
    supported_actions: set[str]
    status: CapabilityStatus = CapabilityStatus.AVAILABLE
    requires_permission: bool = False
    handler: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)
    availability_probe: Callable[["Capability"], tuple[CapabilityStatus, str]] | None = None
    availability_reason: str = "registered"
    last_checked_at: str | None = None
    availability_ttl_seconds: float = 5.0

    def action_metadata(self, action: str) -> dict[str, Any]:
        """Return normalized semantics for one supported action."""
        if action not in self.supported_actions:
            return {}
        defaults = _ACTION_SEMANTICS.get(action, {})
        contract = get_action_contract(action)
        parameters = {}
        if contract is not None:
            for name, rule in contract.parameters.items():
                parameters[name] = {
                    "required": rule.required,
                    "kind": rule.kind,
                    "aliases": list(rule.aliases),
                }
        explicit = self.metadata.get("actions", {}).get(action, {}) if isinstance(self.metadata.get("actions"), dict) else {}
        return {
            "action": action,
            "capability": self.name,
            "description": defaults.get("description", action.replace("_", " ")),
            "side_effect": defaults.get("side_effect", "low"),
            "requires_confirmation": self.requires_permission or defaults.get("requires_confirmation", False),
            "verification": defaults.get("verification", "none"),
            "parameters": parameters,
            **explicit,
        }

    def action_spec(self, action: str) -> ActionSpec | None:
        """Build the canonical executable specification for ``action``."""
        metadata = self.action_metadata(action)
        if not metadata:
            return None
        return ActionSpec(
            action=action,
            capability=self.name,
            description=metadata["description"],
            side_effect=str(metadata["side_effect"]),
            requires_confirmation=bool(metadata["requires_confirmation"]),
            verification=str(metadata["verification"]),
            parameters=dict(metadata.get("parameters") or {}),
        )

    def is_available(self) -> bool:
        return self.status in {CapabilityStatus.AVAILABLE, CapabilityStatus.PARTIAL}

    def availability_snapshot(self) -> AvailabilitySnapshot:
        return AvailabilitySnapshot(
            capability=self.name,
            status=self.status,
            reason=self.availability_reason,
            checked_at=self.last_checked_at or "never",
        )


_ACTION_SEMANTICS: dict[str, dict[str, Any]] = {
    "open_application": {"description": "Launch a desktop application.", "side_effect": "medium", "verification": "window_presence"},
    "focus_window": {"description": "Focus an existing application window.", "side_effect": "low", "verification": "foreground_window"},
    "close_window": {"description": "Close the targeted application window.", "side_effect": "medium", "verification": "window_absence"},
    "type_text": {"description": "Type text into the current target.", "side_effect": "high", "verification": "target_state_or_observation"},
    "press_key": {"description": "Press a keyboard key in the current target.", "side_effect": "high", "verification": "target_state_or_observation"},
    "hotkey": {"description": "Press a keyboard shortcut in the current target.", "side_effect": "high", "verification": "target_state_or_observation"},
    "click": {"description": "Click the targeted desktop element or coordinates.", "side_effect": "high", "verification": "target_state_or_observation"},
    "double_click": {"description": "Double-click the targeted desktop element.", "side_effect": "high", "verification": "target_state_or_observation"},
    "right_click": {"description": "Right-click the targeted desktop element.", "side_effect": "high", "verification": "target_state_or_observation"},
    "scroll": {"description": "Scroll the active desktop surface.", "side_effect": "medium", "verification": "observation"},
    "wait": {"description": "Wait for the environment to settle.", "side_effect": "low", "verification": "timing_only"},
    "navigate": {"description": "Navigate the controlled browser to a URL.", "side_effect": "medium", "verification": "url"},
    "search": {"description": "Search within the controlled browser context.", "side_effect": "medium", "verification": "page_state"},
    "click_web_element": {"description": "Click a specific browser element.", "side_effect": "high", "verification": "page_state"},
    "read_web_page": {"description": "Read the current browser page.", "side_effect": "low", "verification": "page_content"},
    "research_web": {"description": "Search the web, open a relevant result, and read the resulting page.", "side_effect": "medium", "verification": "page_content"},
    "research_web_multi": {"description": "Collect bounded readable evidence from multiple relevant web sources.", "side_effect": "medium", "verification": "multi_source_page_content"},
    "save_file": {"description": "Write content to a local file.", "side_effect": "high", "verification": "file_exists_and_content"},
    "create_file": {"description": "Create a new local file.", "side_effect": "high", "verification": "file_exists"},
    "append_file": {"description": "Append content to an existing local file.", "side_effect": "high", "verification": "file_contains_appended_content"},
    "replace_file_text": {"description": "Replace an exact text occurrence in an existing local file.", "side_effect": "high", "verification": "file_contains_replacement"},
    "read_file": {"description": "Read content from a local file.", "side_effect": "low", "verification": "file_read"},
    "delete_file": {"description": "Delete a local file.", "side_effect": "critical", "requires_confirmation": True, "verification": "file_absence"},
    "list_files": {"description": "List local files in a directory.", "side_effect": "low", "verification": "listing"},
    "email_draft_create": {"description": "Create an email draft.", "side_effect": "medium", "verification": "draft_exists"},
    "email_draft_read": {"description": "Read an email draft.", "side_effect": "low", "verification": "draft_content"},
    "email_draft_update": {"description": "Update an existing email draft.", "side_effect": "medium", "verification": "draft_content"},
    "email_send": {"description": "Send an email through the connected account.", "side_effect": "critical", "requires_confirmation": True, "verification": "message_id"},
    "email_read": {"description": "Read email from the connected account.", "side_effect": "low", "verification": "message_content"},
    "memory_retrieval": {"description": "Retrieve durable memory relevant to the request.", "side_effect": "low", "verification": "memory_result"},
    "memory_update": {"description": "Store a durable memory fact.", "side_effect": "medium", "verification": "memory_presence"},
    "memory_forget": {"description": "Remove a durable memory fact.", "side_effect": "high", "requires_confirmation": True, "verification": "memory_absence"},
}


class CapabilityRegistry:
    """
    Authoritative registry of what ADVI can actually perform.
    Enforces real-world capability boundaries and provides capability context to the Brain.
    """

    def __init__(self) -> None:
        self._capabilities: dict[str, Capability] = {}
        self._action_to_capability: dict[str, str] = {}

    def register(self, capability: Capability) -> None:
        self._capabilities[capability.name] = capability
        for action in capability.supported_actions:
            self._action_to_capability[action] = capability.name

    def set_status(
        self,
        name: str,
        status: CapabilityStatus,
        *,
        reason: str = "runtime status update",
    ) -> bool:
        """Update runtime availability without changing capability semantics."""
        capability = self._capabilities.get(name)
        if capability is None:
            return False
        capability.status = status
        capability.availability_reason = reason
        capability.last_checked_at = datetime.now(timezone.utc).isoformat()
        return True

    def refresh_capability(self, name: str) -> AvailabilitySnapshot | None:
        """Probe one capability and publish the result to the registry."""
        capability = self._capabilities.get(name)
        if capability is None:
            return None
        probe = capability.availability_probe
        if probe is None:
            return capability.availability_snapshot()
        try:
            status, reason = probe(capability)
        except Exception as exc:
            status, reason = CapabilityStatus.UNAVAILABLE, f"availability probe failed: {exc}"
        self.set_status(capability.name, status, reason=reason)
        return capability.availability_snapshot()

    def refresh_all(self, *, force: bool = True) -> list[AvailabilitySnapshot]:
        """Refresh registered capabilities and publish runtime availability snapshots."""
        snapshots = []
        for name in list(self._capabilities):
            snapshot = self.refresh_capability(name) if force else self.refresh_stale(name)
            if snapshot is not None:
                snapshots.append(snapshot)
        return snapshots

    def refresh_stale(self, name: str | None = None) -> list[AvailabilitySnapshot] | AvailabilitySnapshot | None:
        """Refresh only capabilities whose probe result is stale.

        Probes are intentionally cached for a short interval so planning does not
        repeatedly hit the OS, browser, or authentication layer on every prompt.
        """
        names = [name] if name is not None else list(self._capabilities)
        refreshed: list[AvailabilitySnapshot] = []
        now = datetime.now(timezone.utc)
        for cap_name in names:
            capability = self._capabilities.get(cap_name)
            if capability is None:
                continue
            if capability.availability_probe is None:
                continue
            stale = capability.last_checked_at is None
            if not stale:
                try:
                    checked = datetime.fromisoformat(capability.last_checked_at)
                    if checked.tzinfo is None:
                        checked = checked.replace(tzinfo=timezone.utc)
                    stale = (now - checked).total_seconds() >= max(0.0, capability.availability_ttl_seconds)
                except (TypeError, ValueError):
                    stale = True
            if stale:
                snapshot = self.refresh_capability(cap_name)
                if snapshot is not None:
                    refreshed.append(snapshot)
        if name is not None:
            return refreshed[0] if refreshed else self.availability(name)
        return refreshed

    def refresh_for_action(self, action: str, *, force: bool = False) -> AvailabilitySnapshot | None:
        """Refresh the capability owning ``action`` when its runtime state is stale."""
        capability = self.get_capability_for_action(action)
        if capability is None:
            return None
        if force:
            return self.refresh_capability(capability.name)
        return self.refresh_stale(capability.name)

    def availability(self, name: str) -> AvailabilitySnapshot | None:
        capability = self._capabilities.get(name)
        return capability.availability_snapshot() if capability else None

    def availability_summary(self) -> str:
        """Compact authoritative runtime availability summary."""
        lines = []
        for capability in self._capabilities.values():
            lines.append(
                f"- {capability.name}: {capability.status.value} ({capability.availability_reason})"
            )
        return "\n".join(lines) or "- (no capabilities registered)"

    def get(self, name: str) -> Capability | None:
        return self._capabilities.get(name)

    def get_capability_for_action(self, action: str) -> Capability | None:
        cap_name = self._action_to_capability.get(action)
        if cap_name:
            return self._capabilities.get(cap_name)
        return None

    def list_all(self) -> list[Capability]:
        return list(self._capabilities.values())

    def list_available(self) -> list[Capability]:
        return [c for c in self._capabilities.values() if c.is_available()]

    def is_action_supported(self, action: str) -> bool:
        cap = self.get_capability_for_action(action)
        return cap is not None and cap.is_available()

    def get_action_metadata(self, action: str) -> dict[str, Any] | None:
        spec = self.get_action_spec(action)
        if spec is None:
            return None
        return {
            "action": spec.action,
            "capability": spec.capability,
            "description": spec.description,
            "side_effect": spec.side_effect,
            "requires_confirmation": spec.requires_confirmation,
            "verification": spec.verification,
            "parameters": spec.parameters,
        }

    def get_action_spec(self, action: str) -> ActionSpec | None:
        cap = self.get_capability_for_action(action)
        if cap is None or not cap.is_available():
            return None
        return cap.action_spec(action)

    def list_action_specs(self, *, available_only: bool = True) -> list[ActionSpec]:
        specs: list[ActionSpec] = []
        capabilities = self.list_available() if available_only else self.list_all()
        for cap in capabilities:
            for action in sorted(cap.supported_actions):
                spec = cap.action_spec(action)
                if spec is not None:
                    specs.append(spec)
        return specs

    def actions_for_prompt(self) -> str:
        """Detailed, authoritative action catalogue for planning/replanning."""
        rows = [spec.to_prompt_line() for spec in self.list_action_specs()]
        return "\n".join(rows) or "- (no executable actions currently available)"

    def readiness_report(self):
        """Run a deterministic consistency audit for registered capabilities."""
        from advi.core.capability_readiness import CapabilityReadinessChecker
        return CapabilityReadinessChecker().check(self)

    def summary_for_prompt(self) -> str:
        """Full capability context for the LLM – includes unavailable capabilities so the
        Brain can accurately tell users what ADVI can and cannot do."""
        available_lines = []
        unavailable_lines = []
        for cap in self._capabilities.values():
            actions_list = ", ".join(sorted(cap.supported_actions)) if cap.supported_actions else "none"
            if cap.is_available():
                available_lines.append(
                    f"- **{cap.name}** [{cap.status.value}]: {cap.description} | reason={cap.availability_reason}"
                )
            else:
                unavailable_lines.append(
                    f"- **{cap.name}** [unavailable]: {cap.description} | reason={cap.availability_reason}"
                )
        parts = []
        if available_lines:
            parts.append("Available:\n" + "\n".join(available_lines))
        if unavailable_lines:
            parts.append("Unavailable (do not claim these work):\n" + "\n".join(unavailable_lines))
        return "\n\n".join(parts)


def _probe_always_available(capability: Capability) -> tuple[CapabilityStatus, str]:
    return CapabilityStatus.AVAILABLE, "built-in capability"


def _probe_desktop(capability: Capability) -> tuple[CapabilityStatus, str]:
    if capability.handler is None:
        return CapabilityStatus.UNAVAILABLE, "desktop handler is unavailable"
    try:
        import pyautogui
        if os.name != "nt" and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            return CapabilityStatus.UNAVAILABLE, "no desktop display session detected"
        _ = pyautogui.size()
        return CapabilityStatus.AVAILABLE, "desktop input/display is reachable"
    except Exception as exc:
        return CapabilityStatus.UNAVAILABLE, f"desktop environment unavailable: {exc}"


def _probe_browser(capability: Capability) -> tuple[CapabilityStatus, str]:
    if capability.handler is None:
        return CapabilityStatus.UNAVAILABLE, "browser handler is unavailable"
    cdp = getattr(capability.handler, "cdp", None)
    if cdp is None:
        return CapabilityStatus.UNAVAILABLE, "browser CDP client is unavailable"
    try:
        tabs = cdp.list_tabs()
        if tabs:
            return CapabilityStatus.AVAILABLE, "Chrome CDP is reachable"
        if getattr(capability.handler, "_ensure_chrome_running", None) is not None:
            return CapabilityStatus.PARTIAL, "Chrome is not connected; capability can attempt launch"
    except Exception as exc:
        return CapabilityStatus.PARTIAL, f"CDP probe failed; launch may still be possible: {exc}"
    return CapabilityStatus.UNAVAILABLE, "Chrome CDP is unavailable"


def _probe_handler(capability: Capability) -> tuple[CapabilityStatus, str]:
    if capability.handler is None:
        return CapabilityStatus.UNAVAILABLE, "capability handler is unavailable"
    checker = getattr(capability.handler, "is_available", None)
    if callable(checker):
        try:
            if checker():
                return CapabilityStatus.AVAILABLE, "handler reports capability available"
            return CapabilityStatus.UNAVAILABLE, "handler reports capability unavailable"
        except Exception as exc:
            return CapabilityStatus.UNAVAILABLE, f"handler availability check failed: {exc}"
    return CapabilityStatus.AVAILABLE, "handler is configured"


def build_default_registry(
    memory: Any = None,
    retriever: Any = None,
    gmail_service: Any = None,
) -> CapabilityRegistry:
    """Construct and configure the authoritative CapabilityRegistry with all ADVI capabilities."""
    registry = CapabilityRegistry()

    # 1. Desktop Capability
    try:
        from advi.capabilities.desktop.executor import DesktopCapability
        desktop_cap = DesktopCapability()
        registry.register(
            Capability(
                name="desktop_control",
                description="Control desktop applications, focus windows, type text, press keys, and mouse automation.",
                supported_actions=desktop_cap.SUPPORTED_ACTIONS,
                status=CapabilityStatus.AVAILABLE,
                handler=desktop_cap,
                availability_probe=_probe_desktop,
                availability_reason="initially registered; runtime probe pending",
            )
        )
    except Exception as exc:
        registry.register(
            Capability(
                name="desktop_control",
                description="Desktop automation unavailable.",
                supported_actions=set(),
                status=CapabilityStatus.UNAVAILABLE,
            )
        )

    # 2. Browser Capability
    try:
        from advi.capabilities.browser.executor import BrowserCapability
        browser_cap = BrowserCapability()
        registry.register(
            Capability(
                name="browser_control",
                description="Automate Chrome via DevTools Protocol (CDP): navigate websites, search in-page, click elements.",
                supported_actions=browser_cap.SUPPORTED_ACTIONS,
                status=CapabilityStatus.AVAILABLE,
                handler=browser_cap,
                availability_probe=_probe_browser,
                availability_reason="initially registered; runtime probe pending",
            )
        )
    except Exception as exc:
        registry.register(
            Capability(
                name="browser_control",
                description="Browser automation unavailable.",
                supported_actions=set(),
                status=CapabilityStatus.UNAVAILABLE,
            )
        )

    # 3. Filesystem Capability
    try:
        from advi.capabilities.files.executor import FileCapability
        file_cap = FileCapability()
        registry.register(
            Capability(
                name="file_management",
                description="Save, read, create, delete, and verify local files (especially on Desktop).",
                supported_actions=file_cap.SUPPORTED_ACTIONS,
                status=CapabilityStatus.AVAILABLE,
                handler=file_cap,
                availability_probe=_probe_handler,
                availability_reason="initially registered; runtime probe pending",
            )
        )
    except Exception as exc:
        registry.register(
            Capability(
                name="file_management",
                description="File capability unavailable.",
                supported_actions=set(),
                status=CapabilityStatus.UNAVAILABLE,
            )
        )

    # 4. Gmail Capability
    try:
        from advi.capabilities.gmail.executor import GmailCapability
        gmail_cap = GmailCapability(service=gmail_service)
        status = CapabilityStatus.AVAILABLE if gmail_service is not None else CapabilityStatus.UNAVAILABLE
        registry.register(
            Capability(
                name="email",
                description="Draft, read, update, and send email via connected Gmail account.",
                supported_actions=gmail_cap.SUPPORTED_ACTIONS,
                status=status,
                requires_permission=True,
                handler=gmail_cap,
                availability_probe=_probe_handler,
                availability_reason="initially registered; runtime probe pending",
            )
        )
    except Exception as exc:
        pass

    # 5. Memory Capability
    try:
        from advi.capabilities.memory.executor import MemoryCapability
        mem_cap = MemoryCapability(memory=memory, retriever=retriever)
        status = CapabilityStatus.AVAILABLE if (memory is not None or retriever is not None) else CapabilityStatus.UNAVAILABLE
        registry.register(
            Capability(
                name="memory",
                description="Remember user facts, preferences, and retrieve durable contextual memories.",
                supported_actions=mem_cap.SUPPORTED_ACTIONS,
                status=status,
                handler=mem_cap,
                availability_probe=_probe_handler,
                availability_reason="initially registered; runtime probe pending",
            )
        )
    except Exception as exc:
        pass

    # Publish actual runtime state at construction time. Probes are deterministic and
    # do not launch applications or mutate external state.
    registry.refresh_all()
    return registry


default_registry = build_default_registry()
