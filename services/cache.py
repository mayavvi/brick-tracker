"""In-memory LRU cache backed by file mtime for invalidation."""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from pathlib import Path

from models import TaskItem, TrackerFileInfo
from services.parser import parse_tracker_file

logger = logging.getLogger(__name__)

MAX_CACHE_ENTRIES: int = 128


class _CacheEntry:
    __slots__ = ("mtime", "tasks")

    def __init__(self, mtime: float, tasks: list[TaskItem]) -> None:
        self.mtime = mtime
        self.tasks = tasks


class TrackerCache:
    """Thread-safe LRU cache that stores parsed tasks keyed by file path.

    - Entries are automatically invalidated when the file's mtime changes.
    - Oldest entries are evicted when the cache exceeds ``max_entries``.
    """

    def __init__(self, max_entries: int = MAX_CACHE_ENTRIES) -> None:
        self._max = max_entries
        self._store: OrderedDict[str, _CacheEntry] = OrderedDict()
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
                self._store.move_to_end(info.file_path)
                return entry.tasks

        tasks = parse_tracker_file(info)

        with self._lock:
            self._store[info.file_path] = _CacheEntry(current_mtime, tasks)
            self._store.move_to_end(info.file_path)
            while len(self._store) > self._max:
                evicted_key, _ = self._store.popitem(last=False)
                logger.debug("LRU evicted: %s", evicted_key)

        logger.debug("Cache miss / refreshed: %s (%d tasks)", info.file_name, len(tasks))
        return tasks

    def invalidate(self, file_path: str | None = None) -> None:
        """Drop one entry or the entire cache."""
        with self._lock:
            if file_path:
                self._store.pop(file_path, None)
            else:
                self._store.clear()

    @property
    def size(self) -> int:
        """Current number of cached entries."""
        return len(self._store)


tracker_cache = TrackerCache()
