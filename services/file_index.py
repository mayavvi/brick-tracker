"""Program/log indexing and search helpers for file-compare module."""

from __future__ import annotations

import logging
import re
import threading
import time
from pathlib import Path
from typing import Literal

from config import CACHE_TTL_SECONDS, PROJECTS_BASE_PATH
from models import FileEntry
from services.scanner import discover_studies

logger = logging.getLogger(__name__)

_TARGET_SUFFIXES = {".sas", ".log", ".lst"}


class _FileIndexCache:
    """Thread-safe TTL cache for per-study file index."""

    def __init__(self, ttl: int = CACHE_TTL_SECONDS) -> None:
        self._ttl = ttl
        self._store: dict[str, tuple[float, list[FileEntry]]] = {}
        self._lock = threading.Lock()

    def get(self, study_id: str) -> list[FileEntry] | None:
        with self._lock:
            entry = self._store.get(study_id)
            if entry is None:
                return None
            ts, data = entry
            if time.monotonic() - ts > self._ttl:
                del self._store[study_id]
                return None
            return data

    def put(self, study_id: str, data: list[FileEntry]) -> None:
        with self._lock:
            self._store[study_id] = (time.monotonic(), data)

    def invalidate(self) -> None:
        with self._lock:
            self._store.clear()
        with _dir_lock:
            _dir_cache.clear()


file_index_cache = _FileIndexCache()

_dir_cache: dict[str, Path] = {}
_dir_lock = threading.Lock()


def build_index(study_id: str) -> list[FileEntry]:
    """Build or return cached file index for one study."""
    sid = study_id.strip()
    if not sid:
        return []

    cached = file_index_cache.get(sid)
    if cached is not None:
        return cached

    study_dir = _resolve_study_dir(sid)
    out: list[FileEntry] = []
    t0 = time.monotonic()

    for f in study_dir.rglob("*"):
        if not f.is_file():
            continue
        if _is_archive_file(f, study_dir):
            continue
        suffix = f.suffix.lower()
        if suffix not in _TARGET_SUFFIXES:
            continue
        stat = f.stat()
        rel_path = f.relative_to(PROJECTS_BASE_PATH).as_posix()
        rel_in_study = f.relative_to(study_dir).as_posix()
        task = rel_in_study.split("/", 1)[0] if rel_in_study else sid
        out.append(
            FileEntry(
                abs_path=str(f.resolve()),
                rel_path=rel_path,
                study_id=sid,
                task=task,
                role=_infer_role(rel_in_study),
                kind=_infer_kind(suffix),
                size=stat.st_size,
                mtime=stat.st_mtime,
            )
        )

    out.sort(key=lambda x: x.mtime, reverse=True)
    file_index_cache.put(sid, out)

    elapsed = int((time.monotonic() - t0) * 1000)
    logger.info("Indexed %d files for study=%s in %d ms", len(out), sid, elapsed)
    return out


def search(
    query: str,
    study_id: str | None = None,
    kind: Literal["sas", "log", "lst", "other"] | None = None,
    role: Literal["main", "qc", "unknown"] | None = None,
    limit: int = 100,
) -> list[FileEntry]:
    """Search indexed files with exact priority + contiguous match + regex."""
    if study_id:
        candidates = build_index(study_id)
    else:
        candidates: list[FileEntry] = []
        for s in discover_studies(PROJECTS_BASE_PATH):
            try:
                candidates.extend(build_index(s.study_id))
            except Exception:
                logger.exception("Skipping index build for study=%s", s.study_id)

    q_raw = query.strip()
    q_lower = q_raw.lower()
    regex = _compile_regex_query(q_raw)
    scored: list[tuple[int, float, FileEntry]] = []

    for item in candidates:
        if kind and item.kind != kind:
            continue
        if role and item.role != role:
            continue
        score = _search_score(item, q_lower, regex)
        if score is None:
            continue
        scored.append((score, -item.mtime, item))

    scored.sort(key=lambda x: (x[0], x[1], x[2].rel_path.lower()))
    return [x[2] for x in scored[: max(1, limit)]]


def get_tree(study_id: str) -> dict:
    """Return task/folder/file nested structure for tree rendering."""
    sid = study_id.strip()
    study_dir = _resolve_study_dir(sid)
    indexed = build_index(sid)

    task_map: dict[str, dict[str, list[FileEntry]]] = {}
    for item in indexed:
        rel_in_study = Path(item.abs_path).relative_to(study_dir).as_posix()
        parent = str(Path(rel_in_study).parent).replace("\\", "/")
        if parent == ".":
            parent = item.task
        task_map.setdefault(item.task, {}).setdefault(parent, []).append(item)

    tasks: list[dict] = []
    for task_name in sorted(task_map):
        folder_rows: list[dict] = []
        folder_map = task_map[task_name]
        for folder in sorted(folder_map):
            files = sorted(folder_map[folder], key=lambda x: x.rel_path.lower())
            folder_rows.append(
                {
                    "path": folder,
                    "files": [f.model_dump() for f in files],
                }
            )
        tasks.append({"task": task_name, "folders": folder_rows})

    return {
        "study_id": sid,
        "total_files": len(indexed),
        "tasks": tasks,
    }


def _resolve_study_dir(study_id: str) -> Path:
    with _dir_lock:
        if study_id in _dir_cache:
            return _dir_cache[study_id]
    for s in discover_studies(PROJECTS_BASE_PATH):
        if s.study_id == study_id:
            path = (PROJECTS_BASE_PATH / s.compound / s.study_id).resolve()
            with _dir_lock:
                _dir_cache[study_id] = path
            return path
    raise FileNotFoundError(f"Study not found: {study_id}")


def _infer_kind(suffix: str) -> Literal["sas", "log", "lst", "other"]:
    s = suffix.lower()
    if s == ".sas":
        return "sas"
    if s == ".log":
        return "log"
    if s == ".lst":
        return "lst"
    return "other"


def _infer_role(rel_in_study: str) -> Literal["main", "qc", "unknown"]:
    parts = [p.lower() for p in rel_in_study.replace("\\", "/").split("/") if p]
    if any(("qcprog" in p) or (p == "qc") or p.startswith("qc_") for p in parts):
        return "qc"
    if parts:
        return "main"
    return "unknown"


def _search_score(
    item: FileEntry,
    q_lower: str,
    regex: re.Pattern[str] | None,
) -> int | None:
    """Return match score (lower is better), or None when not matched."""
    if not q_lower and regex is None:
        return 90

    rel_lower = item.rel_path.lower()
    name_lower = Path(item.rel_path).name.lower()
    rel_text = item.rel_path
    name_text = Path(item.rel_path).name

    if regex is not None:
        if regex.fullmatch(name_text):
            return 0
        if regex.fullmatch(rel_text):
            return 1
        if regex.search(name_text):
            return 2
        if regex.search(rel_text):
            return 3
        return None

    if name_lower == q_lower:
        return 0
    if rel_lower == q_lower:
        return 1
    if rel_lower.endswith("/" + q_lower):
        return 2
    if name_lower.startswith(q_lower):
        return 3
    if q_lower in name_lower:
        return 4
    if q_lower in rel_lower:
        return 5
    return None


def _is_archive_file(path: Path, study_dir: Path) -> bool:
    """True when file lives under any archive-like folder."""
    try:
        rel_parts = [p.lower() for p in path.relative_to(study_dir).parts[:-1]]
    except Exception:
        rel_parts = [p.lower() for p in path.parts[:-1]]
    return any("archive" in part for part in rel_parts)


def _compile_regex_query(query: str) -> re.Pattern[str] | None:
    """Compile query to regex when regex syntax is used.

    Supported forms:
    - re:<pattern>
    - /<pattern>/<flags>, flags in {i, m, s}
    """
    q = query.strip()
    if not q:
        return None

    pattern = ""
    flags = 0
    is_regex = False

    if q.startswith("re:"):
        is_regex = True
        pattern = q[3:]
        flags = re.IGNORECASE
    elif len(q) >= 2 and q.startswith("/") and "/" in q[1:]:
        last = q.rfind("/")
        if last > 0:
            is_regex = True
            pattern = q[1:last]
            raw_flags = q[last + 1:]
            for ch in raw_flags:
                if ch == "i":
                    flags |= re.IGNORECASE
                elif ch == "m":
                    flags |= re.MULTILINE
                elif ch == "s":
                    flags |= re.DOTALL
                elif ch:
                    raise ValueError(f"不支持的正则 flag: {ch}")

    if not is_regex:
        return None
    if not pattern:
        raise ValueError("正则表达式不能为空")

    try:
        return re.compile(pattern, flags)
    except re.error as exc:
        raise ValueError(f"正则表达式无效: {exc}") from exc
