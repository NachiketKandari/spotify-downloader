"""
Keeps the server light. Three jobs:

1. `download_slot()` — one global queue (semaphore) shared by every download
   job, so ten clicked playlists become ten sequential tracks, not ten
   parallel ffmpeg runs.
2. `remove_after_delivery()` — files leave the server once the user's browser
   has received them (see the streaming responses in main.py).
3. `sweep_once()` / `start_cleanup_thread()` — anything never downloaded is
   deleted after DOWNLOAD_TTL_HOURS, so a forgotten ZIP cannot fill the disk.

Everything is env-tunable; defaults are the "very light" settings.
"""

import os
import shutil
import threading
import time
from contextlib import contextmanager

DOWNLOAD_ROOT = "downloads"

# 1 = delete a file/folder once it has been fully streamed to the browser.
DELETE_AFTER_DOWNLOAD = os.environ.get("DELETE_AFTER_DOWNLOAD", "1").lower() not in ("0", "false", "no")

# How many download jobs may run at the same time (across all users).
MAX_CONCURRENT_JOBS = max(1, int(os.environ.get("MAX_CONCURRENT_JOBS", "1")))

# Delete leftover downloads after this many hours. 0 disables the sweep.
DOWNLOAD_TTL_HOURS = float(os.environ.get("DOWNLOAD_TTL_HOURS", "48"))

_slots = threading.Semaphore(MAX_CONCURRENT_JOBS)

# Paths currently being streamed to a browser; the sweep must not touch these.
_active_paths = set()


@contextmanager
def download_slot(state=None):
    """
    Wait for a free download slot.

    When the queue is busy the job logs a line (so the UI can explain the
    pause) instead of silently hanging.
    """
    if not _slots.acquire(blocking=False):
        if state is not None:
            state.logs.append("Waiting for another download to finish...")
            state.current_track = ""
        _slots.acquire()
    try:
        yield
    finally:
        _slots.release()


def mark_active(path: str) -> None:
    _active_paths.add(os.path.abspath(path))


def unmark_active(path: str) -> None:
    _active_paths.discard(os.path.abspath(path))


def _is_active(path: str) -> bool:
    target = os.path.abspath(path)
    return any(
        target == active or target.startswith(active + os.sep) or active.startswith(target + os.sep)
        for active in tuple(_active_paths)
    )


def remove_after_delivery(path: str) -> None:
    """Delete a delivered file or folder (no-op when DELETE_AFTER_DOWNLOAD=0)."""
    if not DELETE_AFTER_DOWNLOAD:
        return
    try:
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
            print(f"Removed delivered folder: {path}")
        elif os.path.exists(path):
            os.remove(path)
            print(f"Removed delivered file: {path}")
    except OSError as e:
        print(f"Cleanup error for {path}: {e}")


def _newest_mtime(path: str) -> float:
    """Newest mtime anywhere in the tree (top-level mtimes go stale in nested folders)."""
    newest = os.path.getmtime(path)
    for root, dirs, files in os.walk(path):
        for name in (*dirs, *files):
            try:
                newest = max(newest, os.path.getmtime(os.path.join(root, name)))
            except OSError:
                pass
    return newest


def sweep_once(now: float = None) -> list:
    """Delete download folders older than the TTL; returns the removed paths."""
    if DOWNLOAD_TTL_HOURS <= 0 or not os.path.isdir(DOWNLOAD_ROOT):
        return []

    cutoff = (now or time.time()) - DOWNLOAD_TTL_HOURS * 3600
    removed = []
    for name in os.listdir(DOWNLOAD_ROOT):
        path = os.path.join(DOWNLOAD_ROOT, name)
        if not os.path.isdir(path) or _is_active(path):
            continue
        try:
            stale = _newest_mtime(path) < cutoff
        except OSError:
            continue
        if stale:
            shutil.rmtree(path, ignore_errors=True)
            removed.append(path)
    return removed


def start_cleanup_thread() -> None:
    """Hourly background sweep; 0 TTL or CLEANUP=0 disables it."""
    if DOWNLOAD_TTL_HOURS <= 0 or os.environ.get("CLEANUP", "1").lower() in ("0", "false", "no"):
        return

    def loop():
        while True:
            time.sleep(3600)
            for path in sweep_once():
                print(f"cleanup: removed stale {path}")

    threading.Thread(target=loop, daemon=True, name="download-cleanup").start()
