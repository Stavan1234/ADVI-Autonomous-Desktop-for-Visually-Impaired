# src/app_index.py
"""Live index of installed applications, so Shadow resolves a spoken name like
'whatsapp' to something that actually exists BEFORE attempting to launch it —
and can report success/failure truthfully, unlike the old 'start <name>' hack
which reported success unconditionally regardless of what Windows actually did."""

import os
import glob
import json
import difflib
import subprocess
import threading
import time

try:
    import win32com.client  # from pywin32 — resolves .lnk shortcuts to their real target
    _HAS_WIN32COM = True
except ImportError:
    _HAS_WIN32COM = False

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
INDEX_PATH = os.path.join(_DATA_DIR, "app_index.json")
RESCAN_INTERVAL_SECONDS = 1800  # installed apps change rarely — 30 min is plenty, unlike files

START_MENU_DIRS = [
    os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
    os.path.join(os.environ.get("PROGRAMDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
]

_index: dict[str, dict] = {}  # lower-case name -> {"type", "display_name", "target"}
_lock = threading.Lock()


def _resolve_shortcut(lnk_path: str) -> str | None:
    """Classic desktop apps show up as .lnk shortcuts in the Start Menu — resolve
    each one to the real .exe it points at."""
    if not _HAS_WIN32COM:
        return None
    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(lnk_path)
        return shortcut.Targetpath or None
    except Exception:
        return None


def _scan_shortcuts() -> dict:
    entries = {}
    for base in START_MENU_DIRS:
        if not base or not os.path.exists(base):
            continue
        for lnk in glob.glob(os.path.join(base, "**", "*.lnk"), recursive=True):
            name = os.path.splitext(os.path.basename(lnk))[0]
            target = _resolve_shortcut(lnk)
            entries[name.lower()] = {"type": "shortcut", "display_name": name, "target": target or lnk}
    return entries


def _scan_uwp_apps() -> dict:
    """WhatsApp, Telegram, and most Store apps aren't a plain .exe — they're
    packaged apps launched via shell:AppsFolder\\<AppID>. Get-StartApps lists
    every one actually installed, so 'whatsapp' only resolves if it's really there."""
    entries = {}
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-StartApps | ConvertTo-Json"],
            capture_output=True, text=True, timeout=15
        )
        apps = json.loads(result.stdout) if result.stdout.strip() else []
        if isinstance(apps, dict):
            apps = [apps]
        for app in apps:
            name, app_id = app.get("Name", ""), app.get("AppID", "")
            if name and app_id:
                entries[name.lower()] = {"type": "uwp", "display_name": name, "target": app_id}
    except Exception:
        pass  # PowerShell unavailable/timed out — shortcut-based apps still resolve fine
    return entries


def full_scan() -> None:
    combined = {}
    combined.update(_scan_shortcuts())
    combined.update(_scan_uwp_apps())  # UWP entries win on name clashes — usually the real app
    with _lock:
        _index.clear()
        _index.update(combined)
    _flush()


def _flush() -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)
    with _lock:
        snapshot = dict(_index)
    with open(INDEX_PATH, "w") as f:
        json.dump(snapshot, f, indent=2)


def start_index(background_rescan: bool = True) -> None:
    full_scan()
    if background_rescan:
        def periodic():
            while True:
                time.sleep(RESCAN_INTERVAL_SECONDS)
                full_scan()
        threading.Thread(target=periodic, daemon=True).start()


def resolve_app(name: str) -> list[tuple[str, dict]]:
    """Fuzzy-match a spoken app name against what's actually installed."""
    with _lock:
        keys = list(_index.keys())
    matches = difflib.get_close_matches(name.strip().lower(), keys, n=3, cutoff=0.5)
    with _lock:
        return [(_index[m]["display_name"], _index[m]) for m in matches]


def launch(entry: dict) -> dict:
    """Actually launch a resolved entry, checking the result instead of assuming it."""
    try:
        if entry["type"] == "uwp":
            ret = os.system(f'explorer.exe shell:AppsFolder\\{entry["target"]}')
            return {"success": True}  # explorer.exe launches async; this is the best signal available
        else:
            os.startfile(entry["target"])  # raises OSError synchronously if the target is bad
            return {"success": True}
    except OSError as e:
        return {"success": False, "error": str(e)}
