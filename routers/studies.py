"""API routes for compound / study discovery."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Query
from pydantic import BaseModel

from config import PROJECTS_BASE_PATH
from models import StudyInfo
from services.cache import tracker_cache
from services.scanner import (
    discover_compounds,
    discover_studies,
    search_studies,
    study_dir_cache,
)

router = APIRouter(prefix="/api", tags=["studies"])


@router.get("/compounds", response_model=list[str])
def list_compounds() -> list[str]:
    """Return all compound folder names."""
    return discover_compounds(PROJECTS_BASE_PATH)


@router.get("/studies", response_model=list[StudyInfo])
def list_studies(compound: str | None = Query(None)) -> list[StudyInfo]:
    """Return studies, optionally filtered by compound."""
    return discover_studies(PROJECTS_BASE_PATH, compound)


@router.get("/studies/search", response_model=list[StudyInfo])
def search(q: str = Query("", min_length=1)) -> list[StudyInfo]:
    """Fuzzy-search compounds / studies by keyword."""
    return search_studies(PROJECTS_BASE_PATH, q)


class RefreshResult(BaseModel):
    message: str


@router.post("/cache/refresh", response_model=RefreshResult)
def refresh_cache() -> RefreshResult:
    """Clear the directory scan cache and tracker parse cache.

    After this call the next request will re-scan the filesystem and
    pick up newly added / removed studies and tracker files.
    """
    study_dir_cache.invalidate()
    tracker_cache.invalidate()
    return RefreshResult(message="缓存已刷新，新的项目和文件变动将在下次请求时生效")


class ScanDiag(BaseModel):
    compound: str
    studies_found: int
    studies: list[str]
    tracker_files_total: int
    error: str


@router.get("/debug/scan-compound", response_model=ScanDiag)
def debug_scan_compound(compound: str = Query(...)) -> ScanDiag:
    """Diagnostic: scan one compound only and return what was found."""
    result = ScanDiag(
        compound=compound,
        studies_found=0,
        studies=[],
        tracker_files_total=0,
        error="",
    )
    try:
        studies = discover_studies(PROJECTS_BASE_PATH, compound)
        result.studies_found = len(studies)
        result.studies = [s.study_id for s in studies]
        result.tracker_files_total = sum(len(s.tracker_files) for s in studies)
    except Exception as exc:
        result.error = f"{type(exc).__name__}: {exc}"
    return result


class StorageDiag(BaseModel):
    projects_base_path: str
    path_exists: bool
    is_dir: bool
    readable: bool
    uid: int
    gid: int
    entries_sample: list[str]
    error: str


@router.get("/debug/storage", response_model=StorageDiag)
def debug_storage() -> StorageDiag:
    """Diagnostic endpoint — check filesystem access to PROJECTS_BASE_PATH."""
    p = PROJECTS_BASE_PATH
    result = StorageDiag(
        projects_base_path=str(p),
        path_exists=False,
        is_dir=False,
        readable=False,
        uid=os.getuid() if hasattr(os, "getuid") else -1,
        gid=os.getgid() if hasattr(os, "getgid") else -1,
        entries_sample=[],
        error="",
    )
    try:
        result.path_exists = p.exists()
        result.is_dir = p.is_dir()
        result.readable = os.access(str(p), os.R_OK)
        if result.is_dir and result.readable:
            entries = sorted(e.name for e in p.iterdir() if not e.name.startswith("."))
            result.entries_sample = entries[:20]
    except Exception as exc:
        result.error = f"{type(exc).__name__}: {exc}"
    return result
