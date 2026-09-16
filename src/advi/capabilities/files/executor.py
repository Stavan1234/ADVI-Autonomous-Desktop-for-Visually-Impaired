from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from advi.core.action_plan import Action, ExecutionResult

logger = logging.getLogger(__name__)


class FileCapability:
    """
    Filesystem Capability.
    Provides direct local file creation, reading, and path resolution (e.g. Desktop folder).
    """

    SUPPORTED_ACTIONS = {
        "save_file",
        "create_file",
        "append_file",
        "replace_file_text",
        "read_file",
        "delete_file",
        "list_files",
    }

    def __init__(self) -> None:
        self.desktop_dir = self._get_desktop_dir()

    @staticmethod
    def _get_desktop_dir() -> Path:
        userprofile = os.environ.get("USERPROFILE")
        if userprofile:
            desktop = Path(userprofile) / "Desktop"
            if desktop.exists():
                return desktop
        return Path.home() / "Desktop"

    def resolve_path(self, target_path: str) -> Path:
        """Resolve a path, defaulting simple filenames or 'desktop/filename' to Desktop directory."""
        p = Path(target_path)
        if p.is_absolute():
            return p

        # Check if user mentioned Desktop
        parts = p.parts
        if parts and parts[0].lower() == "desktop":
            return self.desktop_dir / Path(*parts[1:])

        # Default relative files to Desktop for desktop assistant convenience
        return self.desktop_dir / p

    def execute(self, action: Action) -> ExecutionResult:
        handler = getattr(self, f"_execute_{action.action}", None)
        if handler is None:
            return ExecutionResult(
                action=action.action,
                success=False,
                error=f"Unsupported file action: {action.action}",
            )

        try:
            return handler(action)
        except Exception as exc:
            logger.exception("File action failed: %s", action.action)
            return ExecutionResult(
                action=action.action,
                success=False,
                error=str(exc),
            )

    def _execute_save_file(self, action: Action) -> ExecutionResult:
        path_str = action.parameters.get("path") or action.parameters.get("filename") or action.target or ""
        content = action.parameters.get("content") or action.parameters.get("value") or ""

        if not path_str:
            return ExecutionResult(
                action=action.action,
                success=False,
                error="No file path or filename provided.",
            )

        target_file = self.resolve_path(str(path_str))
        target_file.parent.mkdir(parents=True, exist_ok=True)

        target_file.write_text(str(content), encoding="utf-8")
        size = target_file.stat().st_size

        return ExecutionResult(
            action=action.action,
            success=True,
            data=str(target_file),
            human_readable=f"Saved file '{target_file.name}' to {target_file.parent} ({size} bytes).",
            verified=True,
            verification_details={"path": str(target_file), "exists": True, "size_bytes": size},
            metadata={"path": str(target_file), "resolved_path": str(target_file), "size": size},
        )

    def _execute_create_file(self, action: Action) -> ExecutionResult:
        return self._execute_save_file(action)

    def _execute_append_file(self, action: Action) -> ExecutionResult:
        path_str = action.parameters.get("path") or action.parameters.get("filename") or action.target or ""
        content = action.parameters.get("content") or action.parameters.get("value")
        if not path_str:
            return ExecutionResult(action=action.action, success=False, error="No file path or filename provided.")
        if content is None:
            return ExecutionResult(action=action.action, success=False, error="No content provided to append.")

        target_file = self.resolve_path(str(path_str))
        if not target_file.exists():
            return ExecutionResult(action=action.action, success=False, error=f"File not found: {target_file}")

        with target_file.open("a", encoding="utf-8") as handle:
            handle.write(str(content))
        size = target_file.stat().st_size
        return ExecutionResult(
            action=action.action,
            success=True,
            data=str(target_file),
            human_readable=f"Appended {len(str(content))} characters to {target_file.name}.",
            metadata={"path": str(target_file), "resolved_path": str(target_file), "appended_content": str(content), "size": size},
        )

    def _execute_replace_file_text(self, action: Action) -> ExecutionResult:
        path_str = action.parameters.get("path") or action.parameters.get("filename") or action.target or ""
        old_text = action.parameters.get("old_text")
        new_text = action.parameters.get("new_text")
        if not path_str:
            return ExecutionResult(action=action.action, success=False, error="No file path or filename provided.")
        if old_text is None or new_text is None:
            return ExecutionResult(action=action.action, success=False, error="Both old_text and new_text are required.")

        target_file = self.resolve_path(str(path_str))
        if not target_file.exists():
            return ExecutionResult(action=action.action, success=False, error=f"File not found: {target_file}")
        original = target_file.read_text(encoding="utf-8", errors="replace")
        occurrences = original.count(str(old_text))
        if occurrences == 0:
            return ExecutionResult(action=action.action, success=False, error="The requested old_text was not found in the file.")
        updated = original.replace(str(old_text), str(new_text), 1)
        target_file.write_text(updated, encoding="utf-8")
        return ExecutionResult(
            action=action.action,
            success=True,
            data=str(target_file),
            human_readable=f"Replaced one occurrence in {target_file.name}.",
            metadata={"path": str(target_file), "resolved_path": str(target_file), "old_text": str(old_text), "new_text": str(new_text), "occurrences_before": occurrences},
        )

    def _execute_read_file(self, action: Action) -> ExecutionResult:
        path_str = action.parameters.get("path") or action.parameters.get("filename") or action.target or ""
        if not path_str:
            return ExecutionResult(action=action.action, success=False, error="No file path provided.")

        target_file = self.resolve_path(str(path_str))
        if not target_file.exists():
            return ExecutionResult(action=action.action, success=False, error=f"File not found: {target_file}")

        text = target_file.read_text(encoding="utf-8", errors="replace")
        return ExecutionResult(
            action=action.action,
            success=True,
            data=text,
            human_readable=f"Read {len(text)} characters from {target_file.name}.",
            metadata={"path": str(target_file), "resolved_path": str(target_file), "length": len(text)},
        )

    def _execute_delete_file(self, action: Action) -> ExecutionResult:
        path_str = action.parameters.get("path") or action.target or ""
        target_file = self.resolve_path(str(path_str))
        if not target_file.exists():
            return ExecutionResult(action=action.action, success=False, error=f"File not found: {target_file}")

        target_file.unlink()
        return ExecutionResult(
            action=action.action,
            success=True,
            data=str(target_file),
            human_readable=f"Deleted file {target_file.name}.",
            verified=not target_file.exists(),
            verification_details={"path": str(target_file), "exists": target_file.exists()},
            metadata={"path": str(target_file), "resolved_path": str(target_file), "exists": target_file.exists()},
        )

    def _execute_list_files(self, action: Action) -> ExecutionResult:
        dir_str = action.parameters.get("directory") or action.target or ""
        dir_path = self.resolve_path(str(dir_str)) if dir_str else self.desktop_dir
        if not dir_path.is_dir():
            dir_path = dir_path.parent

        files = [f.name for f in dir_path.iterdir() if f.is_file()][:50]
        return ExecutionResult(
            action=action.action,
            success=True,
            data=files,
            human_readable=f"Found {len(files)} files in {dir_path.name}.",
            metadata={"directory": str(dir_path), "count": len(files)},
        )
