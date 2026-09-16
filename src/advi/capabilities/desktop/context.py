from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DesktopContext:
    """
    Persistent desktop & browser execution context maintained during automation.
    Tracks target window handle (HWND), application identity, and browser target tab.
    """
    current_application: str | None = None
    target_hwnd: int | None = None
    chrome_cdp_port: int = 9222
    chrome_process_id: int | None = None
    chrome_window_hwnd: int | None = None
    target_tab_id: str | None = None
    target_tab_url: str | None = None
    target_tab_title: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def reset(self) -> None:
        """Reset context between distinct tasks."""
        self.current_application = None
        self.target_hwnd = None
        self.chrome_process_id = None
        self.chrome_window_hwnd = None
        self.target_tab_id = None
        self.target_tab_url = None
        self.target_tab_title = None
        self.metadata.clear()
        logger.info("DesktopContext reset.")

    def set_target_tab(
        self,
        tab_id: str,
        url: str | None = None,
        title: str | None = None,
    ) -> None:
        self.target_tab_id = str(tab_id)
        if url is not None:
            self.target_tab_url = str(url)
        if title is not None:
            self.target_tab_title = str(title)
        self.current_application = "Chrome"

    def set_chrome_window(self, hwnd: int) -> None:
        self.chrome_window_hwnd = int(hwnd)
        self.target_hwnd = int(hwnd)

    def set_application(self, app_name: str, hwnd: int | None = None) -> None:
        self.current_application = str(app_name).strip()
        if hwnd is not None:
            self.target_hwnd = int(hwnd)
            if self.current_application.lower() in {"chrome", "google chrome"}:
                self.chrome_window_hwnd = int(hwnd)

    def is_chrome_target(self) -> bool:
        if not self.current_application:
            return False
        is_chrome = self.current_application.lower() in {"chrome", "google chrome"}
        return is_chrome and bool(self.target_tab_id)
