# src/app_control.py
from pywinauto import Desktop, keyboard
import win32gui

def get_foreground_window_title() -> str:
    """The safety check from the master spec — know what has focus before acting on it."""
    hwnd = win32gui.GetForegroundWindow()
    return win32gui.GetWindowText(hwnd)

def get_foreground_accessibility_text() -> str | None:
    """Tier 0 for smart OCR — read the actual UIA tree of whatever's focused,
    which is instant and exact when it works, unlike a screenshot."""
    try:
        window = Desktop(backend="uia").window(active_only=True)
        texts = [c.window_text() for c in window.descendants() if c.window_text().strip()]
        return "\n".join(texts) if texts else None
    except Exception:
        return None

def type_into_foreground(text: str) -> dict:
    """Sends keystrokes to whatever currently has focus. Simple and general — works
    across almost any app without per-app-specific automation code, at the cost of
    being less precise than targeting a specific control by name."""
    try:
        keyboard.send_keys(text, with_spaces=True, with_tabs=True, with_newlines=True)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

def click_control(name: str) -> dict:
    """Finds a control by its visible name in the foreground window and clicks it —
    this is what makes 'click Send' or 'click Save' possible without coordinates."""
    try:
        window = Desktop(backend="uia").window(active_only=True)
        control = window.child_window(title_re=f".*{name}.*", control_type="Button")
        control.click_input()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": f"Couldn't find a control matching '{name}': {e}"}
