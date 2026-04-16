"""Service for discovering compounds, studies, and tracker files on disk."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from app.config import TRACKER_KEYWORD
from app.models import StudyInfo, TrackerFileInfo

logger = logging.getLogger(__name__)

_TRACKER_DIR_PATTERN = re.compile(r"^\d+_Tracker$", re.IGNORECASE)


def discover_compounds(base_path: Path) -> list[str]:
    """Return sorted list of compound folder names under *base_path*."""
    if not base_path.is_dir():
        logger.warning("Base path does not exist: %s", base_path)
        return []
    return sorted(
        d.name for d in base_path.iterdir() if d.is_dir() and not d.name.startswith(".")
    )


def discover_studies(base_path: Path, compound: str | None = None) -> list[StudyInfo]:
    """Return ``StudyInfo`` for every study under *compound* (or all compounds)."""
    compounds = [compound] if compound else discover_compounds(base_path)
    results: list[StudyInfo] = []
    for comp in compounds:
        comp_dir = base_path / comp
        if not comp_dir.is_dir():
            continue
        for study_dir in sorted(comp_dir.iterdir()):
            if not study_dir.is_dir():
                continue
            tracker_folder = find_tracker_folder(study_dir)
            tracker_files: list[TrackerFileInfo] = []
            if tracker_folder is not None:
                tracker_files = find_tracker_files(tracker_folder, comp, study_dir.name)
            results.append(
                StudyInfo(
                    compound=comp,
                    study_id=study_dir.name,
                    tracker_files=tracker_files,
                )
            )
    return results


def search_studies(base_path: Path, query: str) -> list[StudyInfo]:
    """Fuzzy-search compounds / studies by keyword (case-insensitive)."""
    q = query.strip().upper()
    all_studies = discover_studies(base_path)
    return [
        s for s in all_studies
        if q in s.compound.upper() or q in s.study_id.upper()
    ]


def find_tracker_folder(study_path: Path) -> Path | None:
    """Locate the ``XX_Tracker`` directory inside ``SP/documents/``."""
    docs_dir = study_path / "SP" / "documents"
    if not docs_dir.is_dir():
        return None
    for child in docs_dir.iterdir():
        if child.is_dir() and _TRACKER_DIR_PATTERN.match(child.name):
            return child
    return None


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
