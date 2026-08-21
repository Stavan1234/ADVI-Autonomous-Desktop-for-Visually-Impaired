# src/file_tool.py
"""Standalone filesystem tool module.

Exposes ``create_folder`` / ``delete_path`` for the Brain's LLM tool
dispatcher, plus ``search_file`` — a local, Groq-free file-search function
that queries the ``fs_index.json`` snapshot (the same data maintained by
fs_index.py) and returns the standard ``(success, message, paths)`` triple
used by the Brain dispatcher.
"""

import json
import os
import shutil

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
INDEX_PATH = os.path.join(_DATA_DIR, "fs_index.json")


def create_folder(path: str) -> dict:
    try:
        os.makedirs(path, exist_ok=False)
        return {"success": True}
    except FileExistsError:
        return {"success": False, "error": "already exists"}


def delete_path(path: str) -> dict:
    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def search_file(filename: str) -> tuple[bool, str, list[str]]:
    """
    Searches fs_index.json for matching files.

    Returns: (success_bool, status_message, list_of_matching_paths)
    """
    filename = (filename or "").strip()
    if not filename:
        return False, "What file name should I look for?", []

    try:
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            index = json.load(f)
    except FileNotFoundError:
        return False, "Filesystem index not found. Try restarting the assistant to rebuild it.", []
    except (json.JSONDecodeError, OSError) as e:
        return False, f"Filesystem index could not be read: {e}", []

    query = filename.lower()
    matches = [
        path
        for path, entry in index.items()
        if query in entry.get("name", "").lower()
    ]

    if not matches:
        return True, f"I didn't find any files matching '{filename}'.", []

    names = ", ".join(os.path.basename(p) for p in matches[:10])
    more = f", and {len(matches) - 10} more" if len(matches) > 10 else ""
    return True, f"Found {len(matches)} file(s) matching '{filename}': {names}.", matches

