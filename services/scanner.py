"""Service for discovering compounds, studies, and tracker files on disk.

Directory scan results are cached with a configurable TTL to avoid
hammering the (possibly network-mounted) filesystem on every request.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from config import CACHE_TTL_SECONDS, TRACKER_KEYWORD
from models import StudyInfo, TrackerFileInfo

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Directory-level TTL cache
# ---------------------------------------------------------------------------

class _StudyDirectoryCache:
    """Thread-safe cache for ``discover_studies()`` results.

    The cache key is *compound* (``None`` means "all compounds").
    Each entry expires after ``ttl`` seconds.  A manual ``invalidate()``
    clears everything immediately so the next call re-scans disk.
    """

    def __init__(self, ttl: int = CACHE_TTL_SECONDS) -> None:
        self._ttl = ttl
        self._store: dict[str | None, tuple[float, list[StudyInfo]]] = {}
        self._lock = threading.Lock()

    def get(self, compound: str | None) -> list[StudyInfo] | None:
        with self._lock:
            entry = self._store.get(compound)
            if entry is None:
                return None
            ts, data = entry
            if time.monotonic() - ts > self._ttl:
                del self._store[compound]
                return None
            return data

    def put(self, compound: str | None, data: list[StudyInfo]) -> None:
        with self._lock:
            self._store[compound] = (time.monotonic(), data)

    def invalidate(self) -> None:
        with self._lock:
            self._store.clear()
        logger.info("Study directory cache invalidated")


study_dir_cache = _StudyDirectoryCache()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def discover_compounds(base_path: Path) -> list[str]:
    """Return sorted list of compound folder names under *base_path*."""
    if not base_path.is_dir():
        logger.warning("Base path does not exist: %s", base_path)
        return []
    return sorted(
        d.name for d in base_path.iterdir() if d.is_dir() and not d.name.startswith(".")
    )


def discover_studies(base_path: Path, compound: str | None = None) -> list[StudyInfo]:
    """Return ``StudyInfo`` for every study under *compound* (or all).

    Results are served from an in-memory TTL cache when available.
    """
    cached = study_dir_cache.get(compound)
    if cached is not None:
        return cached

    results = _scan_studies(base_path, compound)
    study_dir_cache.put(compound, results)
    return results


def _is_subsequence(query: str, target: str) -> bool:
    """Check if every character in *query* appears in *target* in order."""
    it = iter(target.upper())
    return all(c in it for c in query.upper())


def _matches(query: str, text: str) -> bool:
    """Substring match OR subsequence match (case-insensitive)."""
    t = text.upper()
    return query in t or _is_subsequence(query, t)


def search_studies(base_path: Path, query: str) -> list[StudyInfo]:
    """Fuzzy-search compounds / studies by keyword (case-insensitive).

    Matches both substring (``QLC5508`` in ``QLC5508-201``) and
    subsequence (``QL1706`` matches ``QLC1706``).

    Optimised for network-mounted filesystems: instead of scanning every
    compound, we first check which compound folders match the query and
    only scan those.
    """
    q = query.strip().upper()
    all_compounds = discover_compounds(base_path)

    matching_compounds = [c for c in all_compounds if _matches(q, c)]

    if matching_compounds:
        results: list[StudyInfo] = []
        for comp in matching_compounds:
            results.extend(discover_studies(base_path, comp))
        return results

    # Fallback: query may be a study-ID fragment — scan everything
    all_studies = discover_studies(base_path)
    return [
        s for s in all_studies
        if _matches(q, s.compound) or _matches(q, s.study_id)
    ]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _scan_studies(base_path: Path, compound: str | None = None) -> list[StudyInfo]:
    """Actually walk the filesystem — the expensive part."""
    t0 = time.monotonic()
    compounds = [compound] if compound else discover_compounds(base_path)
    results: list[StudyInfo] = []
    for comp in compounds:
        comp_dir = base_path / comp
        if not comp_dir.is_dir():
            continue
        try:
            study_dirs = sorted(comp_dir.iterdir())
        except PermissionError as exc:
            logger.warning("Cannot list compound dir %s: %s", comp_dir, exc)
            continue
        for study_dir in study_dirs:
            if not study_dir.is_dir():
                continue
            try:
                tracker_folders = find_tracker_folder(study_dir)
                tracker_files: list[TrackerFileInfo] = []
                for tf_dir in tracker_folders:
                    tracker_files.extend(find_tracker_files(tf_dir, comp, study_dir.name))
            except Exception as exc:
                logger.warning("Error scanning study %s: %s", study_dir, exc)
                tracker_files = []
            results.append(
                StudyInfo(
                    compound=comp,
                    study_id=study_dir.name,
                    tracker_files=tracker_files,
                )
            )
    elapsed = (time.monotonic() - t0) * 1000
    logger.info(
        "Directory scan: %d studies across %d compounds in %.0f ms",
        len(results), len(compounds), elapsed,
    )
    return results


def find_tracker_folder(study_path: Path) -> list[Path]:
    """Locate directories whose name contains 'tracker' under ``SP/documents/``.

    Searches both ``SP/documents/`` directly and one level deeper
    (e.g. ``SP/documents/PhaseII/09_Tracker``).
    """
    docs_dir = study_path / "SP" / "documents"
    if not docs_dir.is_dir():
        return []
    results: list[Path] = []
    try:
        children = list(docs_dir.iterdir())
    except (PermissionError, OSError) as exc:
        logger.warning("Cannot list documents dir %s: %s", docs_dir, exc)
        return []
    for child in children:
        if not child.is_dir():
            continue
        if "tracker" in child.name.lower():
            results.append(child)
        else:
            try:
                for grandchild in child.iterdir():
                    if grandchild.is_dir() and "tracker" in grandchild.name.lower():
                        results.append(grandchild)
            except (PermissionError, OSError) as exc:
                logger.warning("Cannot list subdir %s: %s", child, exc)
    return results


def _extract_task_purpose(filename: str) -> str:
    """Extract the task purpose from a tracker filename.

    Examples:
        "QLC5508-201 ...追踪日志-内部使用_dryrun.xlsx" -> "dryrun"
        "QLC5508-301 ...追踪日志-内部使用_ALL_v1.0.xlsx" -> "ALL_v1.0"
        "QLC7401-201 ...追踪日志-内部使用CSR.xlsx" -> "CSR"
    """
    stem = filename.rsplit(".", 1)[0]  # remove extension
    marker = "内部使用"
    idx = stem.find(marker)
    if idx == -1:
        marker = TRACKER_KEYWORD
        idx = stem.find(marker)
    if idx == -1:
        return stem
    suffix = stem[idx + len(marker):]
    return suffix.lstrip("_- ") or stem


def find_tracker_files(
    tracker_folder: Path,
    compound: str,
    study_id: str,
) -> list[TrackerFileInfo]:
    """Return tracker files whose name contains the TRACKER_KEYWORD."""
    results: list[TrackerFileInfo] = []
    for f in tracker_folder.iterdir():
        if not f.is_file():
            continue
        if f.name.startswith("~$"):
            continue
        if f.suffix.lower() not in (".xlsx", ".xls"):
            continue
        if "archive" in str(f.parent).lower():
            continue
        if TRACKER_KEYWORD not in f.name:
            continue
        results.append(
            TrackerFileInfo(
                file_path=str(f),
                file_name=f.name,
                task_purpose=_extract_task_purpose(f.name),
                study_id=study_id,
                compound=compound,
                last_modified=f.stat().st_mtime,
            )
        )
    return results
