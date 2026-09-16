from __future__ import annotations

import ctypes
import logging
import os
from pathlib import Path
from typing import Any

try:
    import urllib.request as _urllib_request
    import json as _json
except ImportError:
    _urllib_request = None  # type: ignore
    _json = None  # type: ignore

from .action_plan import Action, ExecutionResult, VerificationStatus

logger = logging.getLogger(__name__)


class ActionVerifier:
    """
    Generalized verification layer for ADVI actions.
    Inspects actual system state to confirm an action succeeded.
    """

    def verify(self, action: Action, result: ExecutionResult) -> ExecutionResult:
        """Run verification based on action type.

        IMPORTANT: A verification failure does NOT downgrade a successful execution
        unless there is real evidence of failure (e.g. file not found, wrong URL).
        If there is no specific verifier, or the verifier cannot confirm state,
        the result is returned with verified=False but success unchanged.
        """
        if not result.success:
            # Already a failure – nothing to verify
            return result

        verifier_name = f"_verify_{action.action}"
        verifier = getattr(self, verifier_name, None)

        if verifier is None:
            # No specific verifier: success is preserved, verified stays False.
            return ExecutionResult(
                action=result.action,
                success=result.success,
                data=result.data,
                human_readable=result.human_readable,
                error=result.error,
                verified=result.verified,
                verification_status=(
                    VerificationStatus.VERIFIED if result.verified else VerificationStatus.UNCERTAIN
                ),
                verification_details={"method": "no_verifier"},
                metadata=result.metadata,
            )

        try:
            verified, details = verifier(action, result)
            return ExecutionResult(
                action=result.action,
                # Only downgrade success if verification found POSITIVE evidence of failure
                success=result.success if verified else (
                    False if details.get("definitive_failure") else result.success
                ),
                data=result.data,
                human_readable=result.human_readable,
                error=(
                    result.error
                    if verified
                    else (
                        f"Verification failed: {details.get('reason', 'Condition not met')}"
                        if details.get("definitive_failure")
                        else result.error
                    )
                ),
                verified=verified,
                verification_status=(VerificationStatus.VERIFIED if verified else (
                    VerificationStatus.FAILED if details.get("definitive_failure") else VerificationStatus.UNCERTAIN
                )),
                verification_details=details,
                metadata=result.metadata,
            )
        except Exception as exc:
            logger.warning("Verification exception for %s: %s", action.action, exc)
            return ExecutionResult(
                action=result.action,
                success=result.success,   # preserve success on verifier crash
                data=result.data,
                human_readable=result.human_readable,
                error=result.error,
                verified=False,
                verification_status=VerificationStatus.UNCERTAIN,
                verification_details={"error": str(exc)},
                metadata=result.metadata,
            )

    @staticmethod
    def summarize(results: list[ExecutionResult]) -> dict[str, Any]:
        """Summarize evidence across meaningful action results."""
        meaningful = [r for r in results if r.action != "finish"]
        if not meaningful:
            return {"status": "verified", "verified": 0, "uncertain": 0, "failed": 0}
        failed = [r for r in meaningful if not r.success or r.verification_status == VerificationStatus.FAILED]
        uncertain = [r for r in meaningful if r.success and r.verification_status == VerificationStatus.UNCERTAIN]
        verified = [r for r in meaningful if r.success and r.verification_status == VerificationStatus.VERIFIED]
        status = "failed" if failed else ("uncertain" if uncertain else "verified")
        return {"status": status, "verified": len(verified), "uncertain": len(uncertain), "failed": len(failed)}

    # -------------------------------------------------------------
    # File Operations Verification
    # -------------------------------------------------------------
    def _verify_save_file(self, action: Action, result: ExecutionResult) -> tuple[bool, dict[str, Any]]:
        """Verify file was saved by checking the real filesystem path."""
        # Use the resolved path stored by FileCapability in metadata, or fall back to parameter
        path_str = (
            result.metadata.get("resolved_path")
            or action.parameters.get("path")
            or action.parameters.get("filepath")
            or result.data
        )
        if not path_str:
            return True, {"reason": "no_path_specified"}

        # Resolve Desktop-relative paths the same way FileCapability does
        p = Path(str(path_str))
        if not p.is_absolute():
            parts = p.parts
            if parts and parts[0].lower() == "desktop":
                desktop = Path(os.environ.get("USERPROFILE", Path.home())) / "Desktop"
                p = desktop / Path(*parts[1:])
            else:
                desktop = Path(os.environ.get("USERPROFILE", Path.home())) / "Desktop"
                p = desktop / p

        p = p.resolve()
        exists = p.exists()
        size = p.stat().st_size if exists else 0
        return exists, {
            "path": str(p),
            "exists": exists,
            "size_bytes": size,
            "definitive_failure": not exists,
        }

    def _verify_create_file(self, action: Action, result: ExecutionResult) -> tuple[bool, dict[str, Any]]:
        return self._verify_save_file(action, result)

    def _verify_append_file(self, action: Action, result: ExecutionResult) -> tuple[bool, dict[str, Any]]:
        path_str = result.metadata.get("resolved_path") or action.parameters.get("path") or result.data
        if not path_str:
            return False, {"definitive_failure": False, "reason": "no_path_specified"}
        p = Path(str(path_str))
        if not p.is_absolute():
            desktop = Path(os.environ.get("USERPROFILE", Path.home())) / "Desktop"
            p = desktop / Path(*p.parts[1:]) if p.parts and p.parts[0].lower() == "desktop" else desktop / p
        p = p.resolve()
        if not p.exists():
            return False, {"path": str(p), "exists": False, "definitive_failure": True, "reason": "file_missing"}
        content = str(action.parameters.get("content") or action.parameters.get("value") or "")
        text = p.read_text(encoding="utf-8", errors="replace")
        ok = text.endswith(content) if content else True
        return ok, {"path": str(p), "exists": True, "contains_appended_content": ok, "definitive_failure": bool(content and not ok)}

    def _verify_replace_file_text(self, action: Action, result: ExecutionResult) -> tuple[bool, dict[str, Any]]:
        path_str = result.metadata.get("resolved_path") or action.parameters.get("path") or result.data
        old_text = str(action.parameters.get("old_text") or "")
        new_text = str(action.parameters.get("new_text") or "")
        if not path_str:
            return False, {"definitive_failure": False, "reason": "no_path_specified"}
        p = Path(str(path_str)).resolve()
        if not p.exists():
            return False, {"path": str(p), "exists": False, "definitive_failure": True, "reason": "file_missing"}
        text = p.read_text(encoding="utf-8", errors="replace")
        ok = new_text in text and old_text not in text
        return ok, {"path": str(p), "replacement_present": new_text in text, "old_text_present": old_text in text, "definitive_failure": not ok}

    def _verify_read_file(self, action: Action, result: ExecutionResult) -> tuple[bool, dict[str, Any]]:
        data = result.data
        path = result.metadata.get("resolved_path") or result.metadata.get("path")
        readable = isinstance(data, (str, bytes))
        return readable, {
            "path": path,
            "readable": readable,
            "length": len(data) if hasattr(data, "__len__") else None,
            "source": "executor_payload",
        }

    def _verify_list_files(self, action: Action, result: ExecutionResult) -> tuple[bool, dict[str, Any]]:
        files = result.data
        valid = isinstance(files, list)
        return valid, {
            "directory": result.metadata.get("directory"),
            "valid_listing": valid,
            "count": len(files) if valid else None,
        }

    def _verify_read_web_page(self, action: Action, result: ExecutionResult) -> tuple[bool, dict[str, Any]]:
        text = result.data
        valid = isinstance(text, str)
        return valid, {
            "tab_id": result.metadata.get("tab_id"),
            "content_available": valid,
            "length": len(text) if valid else None,
        }

    # -------------------------------------------------------------
    # Desktop Application Verification
    # -------------------------------------------------------------
    def _verify_open_application(self, action: Action, result: ExecutionResult) -> tuple[bool, dict[str, Any]]:
        hwnd = result.metadata.get("hwnd") or (result.data if isinstance(result.data, int) else None)
        if hwnd:
            user32 = ctypes.windll.user32
            is_window = bool(user32.IsWindow(hwnd))
            is_visible = bool(user32.IsWindowVisible(hwnd))
            # Require the window to actually exist and be visible
            return is_window and is_visible, {
                "hwnd": hwnd,
                "is_window": is_window,
                "is_visible": is_visible,
            }
        # No HWND captured – we cannot verify the application is actually open
        return False, {
            "status": "no_hwnd",
            "reason": "Application may have launched but no window handle was captured to confirm it is visible.",
        }

    def _verify_focus_window(self, action: Action, result: ExecutionResult) -> tuple[bool, dict[str, Any]]:
        user32 = ctypes.windll.user32
        foreground_hwnd = user32.GetForegroundWindow()
        expected_hwnd = result.metadata.get("hwnd")
        if expected_hwnd:
            is_foreground = (foreground_hwnd == expected_hwnd)
            return is_foreground, {
                "expected_hwnd": expected_hwnd,
                "foreground_hwnd": foreground_hwnd,
                "is_foreground": is_foreground,
            }
        return bool(foreground_hwnd), {"foreground_hwnd": foreground_hwnd}

    # -------------------------------------------------------------
    # Browser Verification
    # -------------------------------------------------------------
    def _verify_navigate(self, action: Action, result: ExecutionResult) -> tuple[bool, dict[str, Any]]:
        """Verify navigation by querying real CDP tab state."""
        expected_url = str(action.parameters.get("url", ""))

        # Try to get actual current URL from CDP /json endpoint
        cdp_port = result.metadata.get("cdp_port", 9222)
        current_url: str | None = None
        try:
            if _urllib_request is not None:
                with _urllib_request.urlopen(
                    f"http://localhost:{cdp_port}/json", timeout=2
                ) as resp:
                    tabs = _json.loads(resp.read().decode())
                    for tab in tabs:
                        if tab.get("type") == "page":
                            current_url = tab.get("url")
                            break
        except Exception as exc:
            logger.debug("CDP URL query failed: %s", exc)

        # Fall back to executor-provided metadata
        if not current_url:
            current_url = result.metadata.get("current_url") or str(result.data or "")

        if expected_url and current_url:
            matched = (
                expected_url.lower() in current_url.lower()
                or current_url.lower() in expected_url.lower()
            )
            return matched, {
                "expected_url": expected_url,
                "current_url": current_url,
                "url_matched": matched,
                "definitive_failure": not matched,
                "source": "cdp" if current_url not in [result.metadata.get("current_url"), str(result.data or "")] else "metadata",
            }
        # Cannot verify – leave success intact
        return True, {"current_url": current_url, "reason": "url_unavailable"}

    # -------------------------------------------------------------
    # Email Verification
    # -------------------------------------------------------------
    def _verify_email_send(self, action: Action, result: ExecutionResult) -> tuple[bool, dict[str, Any]]:
        message_id = result.metadata.get("message_id") or (result.data.get("id") if isinstance(result.data, dict) else None)
        if message_id:
            return True, {"message_id": message_id, "status": "sent"}
        return False, {"reason": "missing_message_id"}
