from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class ObservedState:
    """Small, JSON-friendly snapshot of observable environment state."""
    platform: str = os.name
    foreground_window: str | None = None
    foreground_hwnd: int | None = None
    application: str | None = None
    browser_url: str | None = None
    browser_title: str | None = None
    files: dict[str, dict[str, Any]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "foreground_window": self.foreground_window,
            "foreground_hwnd": self.foreground_hwnd,
            "application": self.application,
            "browser_url": self.browser_url,
            "browser_title": self.browser_title,
            "files": self.files,
            "metadata": self.metadata,
        }


class StateSource(Protocol):
    def observe(self, context: Any) -> ObservedState:
        ...


class SystemStateSource:
    """Best-effort platform state reader; never raises to the agent."""

    def observe(self, context: Any) -> ObservedState:
        foreground_window = None
        foreground_hwnd = None

        if os.name == "nt":
            try:
                import ctypes

                user32 = ctypes.windll.user32
                hwnd = int(user32.GetForegroundWindow())
                foreground_hwnd = hwnd or None
                if hwnd:
                    length = int(user32.GetWindowTextLengthW(hwnd))
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    foreground_window = buf.value or None
            except Exception:
                pass

        return ObservedState(
            foreground_window=foreground_window,
            foreground_hwnd=foreground_hwnd,
            application=getattr(context, "current_application", None),
            browser_url=getattr(context, "target_tab_url", None),
            browser_title=getattr(context, "target_tab_title", None),
            metadata={
                "target_hwnd": getattr(context, "target_hwnd", None),
                "target_tab_id": getattr(context, "target_tab_id", None),
            },
        )


class FileStateSource:
    """Observe explicitly requested filesystem paths without mutating them."""

    def __init__(self, base_dir: str | Path | None = None) -> None:
        self.base_dir = Path(base_dir) if base_dir else None

    def _resolve(self, value: str | Path) -> Path:
        path = Path(str(value))
        if path.is_absolute():
            return path
        if self.base_dir:
            return (self.base_dir / path).resolve()
        return path.resolve()

    def observe_paths(self, paths: list[str | Path]) -> dict[str, dict[str, Any]]:
        observed: dict[str, dict[str, Any]] = {}
        for raw in paths:
            path = self._resolve(raw)
            try:
                exists = path.exists()
                observed[str(path)] = {
                    "exists": exists,
                    "is_file": path.is_file() if exists else False,
                    "is_dir": path.is_dir() if exists else False,
                    "size_bytes": path.stat().st_size if exists and path.is_file() else None,
                }
            except OSError as exc:
                observed[str(path)] = {"exists": None, "error": str(exc)}
        return observed


class BrowserStateSource:
    """Read browser state from an injected CDP client when available."""

    def __init__(self, cdp: Any | None = None) -> None:
        self.cdp = cdp

    def observe(self, context: Any) -> ObservedState:
        url = getattr(context, "target_tab_url", None)
        title = getattr(context, "target_tab_title", None)
        tab_id = getattr(context, "target_tab_id", None)
        if self.cdp is not None and tab_id:
            try:
                result = self.cdp.evaluate_script(tab_id, "({url: location.href, title: document.title})")
                value = result.get("value", {}) if result else {}
                if isinstance(value, dict):
                    url = value.get("url") or url
                    title = value.get("title") or title
            except Exception:
                pass
        return ObservedState(
            application="Chrome",
            browser_url=url,
            browser_title=title,
            metadata={"target_tab_id": tab_id},
        )


class StateObserver:
    """Composes best-effort observation sources into one stable contract."""

    def __init__(
        self,
        system: SystemStateSource | None = None,
        browser: BrowserStateSource | None = None,
        files: FileStateSource | None = None,
    ) -> None:
        self.system = system or SystemStateSource()
        self.browser = browser
        self.files = files or FileStateSource()

    def observe(
        self,
        context: Any,
        paths: list[str | Path] | None = None,
    ) -> ObservedState:
        system = self.system.observe(context)
        browser = self.browser.observe(context) if self.browser is not None else ObservedState()
        files = self.files.observe_paths(paths or [])

        return ObservedState(
            platform=system.platform,
            foreground_window=system.foreground_window,
            foreground_hwnd=system.foreground_hwnd,
            application=(browser.application or system.application),
            browser_url=(browser.browser_url or system.browser_url),
            browser_title=(browser.browser_title or system.browser_title),
            files=files,
            metadata={**system.metadata, **browser.metadata},
        )


__all__ = [
    "ObservedState",
    "StateObserver",
    "StateSource",
    "SystemStateSource",
    "FileStateSource",
    "BrowserStateSource",
]
