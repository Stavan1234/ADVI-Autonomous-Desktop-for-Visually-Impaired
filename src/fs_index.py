# src/fs_index.py
"""Live filesystem awareness: scans known folders on startup, updates instantly via
watchdog on any change, plus a 5-minute periodic rescan as a safety net. Every query
function here is pure local Python — none of them touch Groq."""

import os
import json
import time
import threading
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
INDEX_PATH = os.path.join(_DATA_DIR, "fs_index.json")
RESCAN_INTERVAL_SECONDS = 300  # 5 minutes, as requested — belt-and-suspenders alongside watchdog

HOME = os.path.expanduser("~")
KNOWN_ROOTS = {
    "desktop": os.path.join(HOME, "Desktop"),
    "documents": os.path.join(HOME, "Documents"),
    "downloads": os.path.join(HOME, "Downloads"),
    "pictures": os.path.join(HOME, "Pictures"),
    "home": HOME,
}

_index: dict[str, dict] = {}
_lock = threading.Lock()


def _entry(path: str) -> dict | None:
    try:
        st = os.stat(path)
        return {
            "path": path,
            "name": os.path.basename(path),
            "ext": os.path.splitext(path)[1].lower().lstrip("."),
            "size": st.st_size,
            "modified": st.st_mtime,
            "is_dir": os.path.isdir(path),
        }
    except (FileNotFoundError, PermissionError):
        return None


def _default_roots() -> list[str]:
    return [KNOWN_ROOTS["desktop"], KNOWN_ROOTS["documents"], KNOWN_ROOTS["downloads"], KNOWN_ROOTS["pictures"]]


def full_scan(roots: list[str] | None = None) -> None:
    roots = roots or _default_roots()
    new_index = {}
    for root in roots:
        if not os.path.exists(root):
            continue
        for dirpath, dirs, files in os.walk(root):
            for name in dirs + files:
                p = os.path.join(dirpath, name)
                entry = _entry(p)
                if entry:
                    new_index[p] = entry
    with _lock:
        _index.clear()
        _index.update(new_index)
    _flush()


def _flush() -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)
    with _lock:
        snapshot = dict(_index)
    with open(INDEX_PATH, "w") as f:
        json.dump(snapshot, f)


class _Handler(FileSystemEventHandler):
    def on_created(self, event):
        entry = _entry(event.src_path)
        if entry:
            with _lock:
                _index[event.src_path] = entry
            _flush()

    def on_deleted(self, event):
        with _lock:
            _index.pop(event.src_path, None)
        _flush()

    def on_modified(self, event):
        entry = _entry(event.src_path)
        if entry:
            with _lock:
                _index[event.src_path] = entry
            _flush()

    def on_moved(self, event):
        with _lock:
            _index.pop(event.src_path, None)
        entry = _entry(event.dest_path)
        if entry:
            with _lock:
                _index[event.dest_path] = entry
        _flush()


def start_watcher(roots: list[str] | None = None) -> Observer:
    """Call this once at startup. Does the initial full scan, then keeps the index
    live via filesystem events, with a periodic rescan as a safety net (Windows can
    occasionally report a rename as delete+create in a way a single watcher misses)."""
    roots = roots or _default_roots()
    full_scan(roots)

    observer = Observer()
    handler = _Handler()
    for root in roots:
        if os.path.exists(root):
            observer.schedule(handler, root, recursive=True)
    observer.start()

    def periodic_rescan():
        while True:
            time.sleep(RESCAN_INTERVAL_SECONDS)
            full_scan(roots)

    threading.Thread(target=periodic_rescan, daemon=True).start()
    return observer


# ── Local query functions — no Groq call, ever ────────────────────────────────

def find_by_extension(ext: str, root_hint: str | None = None) -> list[dict]:
    ext = ext.lower().lstrip(".")
    with _lock:
        results = [e for e in _index.values() if e["ext"] == ext and not e["is_dir"]]
    if root_hint:
        root_path = KNOWN_ROOTS.get(root_hint.lower())
        if root_path:
            results = [e for e in results if e["path"].startswith(root_path)]
    return sorted(results, key=lambda e: e["modified"], reverse=True)


def find_modified_since(cutoff: datetime) -> list[dict]:
    cutoff_ts = cutoff.timestamp()
    with _lock:
        return sorted(
            [e for e in _index.values() if e["modified"] >= cutoff_ts],
            key=lambda e: e["modified"], reverse=True
        )


def search_by_name(query: str) -> list[dict]:
    query = query.lower()
    with _lock:
        return [e for e in _index.values() if query in e["name"].lower()]


def resolve_known_location(name: str) -> str | None:
    """Maps a bare word like 'Desktop' to its real absolute path. This is what fixes
    the 'can't create outside the project folder' bug — bare names now resolve to a
    real known folder instead of silently falling through to abspath()'s cwd default."""
    return KNOWN_ROOTS.get(name.strip().lower())
