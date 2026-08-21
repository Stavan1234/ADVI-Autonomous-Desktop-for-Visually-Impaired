"""Standalone app-launch tool.

Resolves a spoken app name against the installed-app index (built by
app_index.py) and launches it, reporting success/failure truthfully — unlike
the old ``subprocess.Popen(["start", "", name], shell=True)`` hack, which
claimed success unconditionally regardless of what Windows actually did.

Exposes the ``launch_app(name: str) -> tuple[bool, str]`` interface used by the
Brain dispatcher.
"""

import app_index


def launch_app(app_name: str) -> tuple[bool, str]:
    """Resolve and launch an installed application by its common name.

    Returns a ``(success: bool, message: str)`` tuple so callers can speak the
    outcome directly.
    """
    app_name = (app_name or "").strip()
    if not app_name:
        return False, "Which application should I open?"

    # Build the index on demand if it hasn't been scanned yet (e.g. direct use).
    if not app_index.resolve_app(app_name):
        app_index.full_scan()

    candidates = app_index.resolve_app(app_name)
    if not candidates:
        return False, f"I couldn't find an installed app matching '{app_name}'."

    # Candidates come back ordered by difflib closeness; take the best single match.
    display_name, entry = candidates[0]
    result = app_index.launch(entry)
    if result["success"]:
        return True, f"Opened {display_name}."
    return False, f"Couldn't open {display_name}: {result['error']}"

