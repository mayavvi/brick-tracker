"""In-memory cache backed by file mtime for invalidation."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from app.models import TaskItem, TrackerFileInfo
from app.services.parser import parse_tracker_file

logger = logging.getLogger(__name__)


class _CacheEntry:
    __slots__ = ("mtime", "tasks")

    def __init__(self, mtime: float, tasks: list[TaskItem]) -> None:
        self.mtime = mtime
        self.tasks = tasks


class TrackerCache:
    """Thread-safe cache that stores parsed tasks keyed by file path.

    Entries are automatically invalidated when the file's mtime changes.
    """

    def __init__(self) -> None:
        self._store: dict[str, _CacheEntry] = {}
        self._lock = threading.Lock()

    def get_tasks(self, info: TrackerFileInfo) -> list[TaskItem]:
        """Return parsed tasks, using cache when the file has not changed."""
        path = Path(info.file_path)
        try:
            current_mtime = path.stat().st_mtime
        except OSError:
            logger.warning("Cannot stat file: %s", path)
            return []

        with self._lock:
            entry = self._store.get(info.file_path)
            if entry is not None and entry.mtime == current_mtime:
                logger.debug("Cache hit: %s", info.file_name)
                return entry.tasks

        tasks = parse_tracker_file(info)

        with self._lock:
            self._store[info.file_path] = _CacheEntry(current_mtime, tasks)

        logger.debug("Cache miss / refreshed: %s (%d tasks)", info.file_name, len(tasks))
        return tasks

    def invalidate(self, file_path: str | None = None) -> None:
        """Drop one entry or the entire cache."""
        with self._lock:
            if file_path:
                self._store.pop(file_path, None)
            else:
                self._store.clear()


tracker_cache = TrackerCache()
