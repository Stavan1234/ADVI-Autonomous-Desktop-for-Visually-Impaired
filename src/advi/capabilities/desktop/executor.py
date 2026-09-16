from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import time
from pathlib import Path


def _get_pyautogui():
    """Load pyautogui only when a desktop action actually executes."""
    import pyautogui
    return pyautogui
from typing import Any


from advi.core.action_plan import Action, ExecutionResult
from .context import DesktopContext
from .perception import ScreenPerception

logger = logging.getLogger(__name__)


class DesktopCapability:
    """
    Desktop & OS Automation Capability.
    Responsible for launching applications, managing windows, typing,
    hotkeys, mouse clicks, and perception.
    """

    SUPPORTED_ACTIONS = {
        "open_application",
        "close_window",
        "focus_window",
        "type_text",
        "press_key",
        "hotkey",
        "click",
        "double_click",
        "right_click",
        "scroll",
        "wait",
        "finish",
    }

    def __init__(
        self,
        context: DesktopContext | None = None,
        perception: ScreenPerception | None = None,
    ) -> None:
        self.context = context or DesktopContext()
        self.perception = perception or ScreenPerception()

    def execute(self, action: Action) -> ExecutionResult:
        handler = getattr(self, f"_execute_{action.action}", None)
        if handler is None:
            return ExecutionResult(
                action=action.action,
                success=False,
                error=f"Unsupported desktop action: {action.action}",
            )

        try:
            return handler(action)
        except Exception as exc:
            logger.exception("Desktop action execution failed: %s", action.action)
            return ExecutionResult(
                action=action.action,
                success=False,
                error=str(exc),
            )

    # -------------------------------------------------------------
    # Window & Application Launching
    # -------------------------------------------------------------
    def _execute_open_application(self, action: Action) -> ExecutionResult:
        app_name = action.parameters.get("application") or action.target or ""
        app_clean = str(app_name).strip()

        if not app_clean:
            return ExecutionResult(
                action=action.action,
                success=False,
                error="Application name was not specified.",
            )

        # Standard Windows applications
        app_commands = {
            "notepad": "notepad.exe",
            "calculator": "calc.exe",
            "calc": "calc.exe",
            "cmd": "cmd.exe",
            "terminal": "wt.exe",
            "explorer": "explorer.exe",
            "paint": "mspaint.exe",
        }

        cmd = app_commands.get(app_clean.lower(), app_clean)

        try:
            process = subprocess.Popen(
                cmd,
                shell=True,
                creationflags=subprocess.DETACHED_PROCESS if os.name == "nt" else 0,
            )
            time.sleep(1.0)

            # Find matching window
            hwnd = self._find_window_by_name(app_clean)
            if hwnd:
                self.context.set_application(app_clean, hwnd=hwnd)
                self._activate_window(hwnd)

            return ExecutionResult(
                action=action.action,
                success=True,
                data=process.pid,
                human_readable=f"Opened application '{app_clean}' successfully.",
                metadata={"pid": process.pid, "hwnd": hwnd, "application": app_clean},
            )
        except Exception as exc:
            return ExecutionResult(
                action=action.action,
                success=False,
                error=f"Failed to open '{app_clean}': {exc}",
            )

    def _execute_focus_window(self, action: Action) -> ExecutionResult:
        target = action.parameters.get("title") or action.target or self.context.current_application
        hwnd = self.context.target_hwnd

        if not hwnd and target:
            hwnd = self._find_window_by_name(str(target))

        if not hwnd:
            return ExecutionResult(
                action=action.action,
                success=False,
                error=f"Could not locate window to focus: {target}",
            )

        success = self._activate_window(hwnd)
        self.context.target_hwnd = hwnd
        return ExecutionResult(
            action=action.action,
            success=success,
            data=hwnd,
            human_readable=f"Focused window {target} (HWND: {hwnd})",
            metadata={"hwnd": hwnd},
        )

    def _execute_close_window(self, action: Action) -> ExecutionResult:
        hwnd = self.context.target_hwnd or (self._find_window_by_name(action.target) if action.target else None)
        if not hwnd:
            return ExecutionResult(
                action=action.action,
                success=False,
                error="No target window available to close.",
            )

        user32 = ctypes.windll.user32
        WM_CLOSE = 0x0010
        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        time.sleep(0.5)

        self.context.target_hwnd = None
        return ExecutionResult(
            action=action.action,
            success=True,
            human_readable="Closed window successfully.",
        )

    # -------------------------------------------------------------
    # Keyboard & Typing
    # -------------------------------------------------------------
    def _execute_type_text(self, action: Action) -> ExecutionResult:
        pyautogui = _get_pyautogui()
        text = action.parameters.get("value") or action.parameters.get("text")
        if text is None:
            return ExecutionResult(
                action=action.action,
                success=False,
                error="No text value provided to type.",
            )

        # Ensure target window is focused if known
        if self.context.target_hwnd:
            self._activate_window(self.context.target_hwnd)
            time.sleep(0.2)

        pyautogui.write(str(text), interval=0.01)
        time.sleep(0.2)

        return ExecutionResult(
            action=action.action,
            success=True,
            data=str(text),
            human_readable=f"Typed {len(str(text))} characters.",
            metadata={"text_length": len(str(text))},
        )

    def _execute_press_key(self, action: Action) -> ExecutionResult:
        pyautogui = _get_pyautogui()
        key = action.parameters.get("key") or action.parameters.get("value") or action.target
        if not key:
            return ExecutionResult(
                action=action.action,
                success=False,
                error="No key specified.",
            )

        clean_key = str(key).strip().lower()
        if self.context.target_hwnd:
            self._activate_window(self.context.target_hwnd)
            time.sleep(0.1)

        pyautogui.press(clean_key)
        time.sleep(0.1)

        return ExecutionResult(
            action=action.action,
            success=True,
            data=clean_key,
            human_readable=f"Pressed key '{clean_key}'.",
        )

    def _execute_hotkey(self, action: Action) -> ExecutionResult:
        pyautogui = _get_pyautogui()
        keys = action.parameters.get("keys") or action.parameters.get("hotkey")
        if isinstance(keys, str):
            key_list = [k.strip().lower() for k in keys.split("+")]
        elif isinstance(keys, list):
            key_list = [str(k).strip().lower() for k in keys]
        else:
            return ExecutionResult(
                action=action.action,
                success=False,
                error="Invalid hotkey specification.",
            )

        if self.context.target_hwnd:
            self._activate_window(self.context.target_hwnd)
            time.sleep(0.1)

        pyautogui.hotkey(*key_list)
        time.sleep(0.2)

        return ExecutionResult(
            action=action.action,
            success=True,
            data="+".join(key_list),
            human_readable=f"Executed shortcut {'+'.join(key_list)}.",
        )

    # -------------------------------------------------------------
    # Mouse & Perception
    # -------------------------------------------------------------
    def _execute_click(self, action: Action) -> ExecutionResult:
        pyautogui = _get_pyautogui()
        target = action.target or action.parameters.get("target")
        coords = action.parameters.get("coordinates")

        if coords and isinstance(coords, (list, tuple)) and len(coords) >= 2:
            pyautogui.click(coords[0], coords[1])
            return ExecutionResult(
                action=action.action,
                success=True,
                data=coords,
                human_readable=f"Clicked at coordinates {coords}.",
            )

        if target:
            res = self.perception.find(
                target=str(target),
                application=self.context.current_application,
                window_hwnd=self.context.target_hwnd,
            )
            if res.found and res.target is not None:
                if hasattr(res.target, "click_input"):
                    res.target.click_input()
                elif isinstance(res.target, (tuple, list)):
                    pyautogui.click(res.target[0], res.target[1])
                return ExecutionResult(
                    action=action.action,
                    success=True,
                    data=target,
                    human_readable=f"Clicked on '{target}'.",
                )
            return ExecutionResult(
                action=action.action,
                success=False,
                error=f"Could not locate target '{target}' to click.",
            )

        pyautogui.click()
        return ExecutionResult(
            action=action.action,
            success=True,
            human_readable="Clicked mouse at current position.",
        )

    def _execute_double_click(self, action: Action) -> ExecutionResult:
        pyautogui = _get_pyautogui()
        pyautogui.doubleClick()
        return ExecutionResult(
            action=action.action,
            success=True,
            human_readable="Double clicked.",
        )

    def _execute_right_click(self, action: Action) -> ExecutionResult:
        pyautogui = _get_pyautogui()
        pyautogui.rightClick()
        return ExecutionResult(
            action=action.action,
            success=True,
            human_readable="Right clicked.",
        )

    def _execute_scroll(self, action: Action) -> ExecutionResult:
        pyautogui = _get_pyautogui()
        amount = int(action.parameters.get("amount", 300))
        direction = str(action.parameters.get("direction", "down")).lower()
        clicks = -amount if direction == "down" else amount
        pyautogui.scroll(clicks)
        return ExecutionResult(
            action=action.action,
            success=True,
            data=clicks,
            human_readable=f"Scrolled {direction}.",
        )

    def _execute_wait(self, action: Action) -> ExecutionResult:
        duration = float(action.parameters.get("duration") or action.parameters.get("seconds") or 1.0)
        time.sleep(max(0.1, min(duration, 30.0)))
        return ExecutionResult(
            action=action.action,
            success=True,
            data=duration,
            human_readable=f"Waited for {duration:.1f}s.",
        )

    def _execute_finish(self, action: Action) -> ExecutionResult:
        return ExecutionResult(
            action=action.action,
            success=True,
            human_readable="Plan finished.",
        )

    # -------------------------------------------------------------
    # Windows Helpers
    # -------------------------------------------------------------
    @staticmethod
    def _activate_window(hwnd: int) -> bool:
        user32 = ctypes.windll.user32
        if not user32.IsWindow(hwnd):
            return False
        SW_RESTORE = 9
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.2)
        return True

    @staticmethod
    def _find_window_by_name(target_name: str) -> int | None:
        user32 = ctypes.windll.user32
        target_lower = target_name.strip().lower()
        found_hwnd: int | None = None

        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def callback(hwnd, _lparam):
            nonlocal found_hwnd
            if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value.lower()
                if target_lower in title:
                    found_hwnd = int(hwnd)
                    return False
            return True

        user32.EnumWindows(EnumWindowsProc(callback), 0)
        return found_hwnd
