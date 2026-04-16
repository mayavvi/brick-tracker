"""API routes for compound / study discovery."""

from __future__ import annotations

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
async def list_compounds() -> list[str]:
    """Return all compound folder names."""
    return discover_compounds(PROJECTS_BASE_PATH)


@router.get("/studies", response_model=list[StudyInfo])
async def list_studies(compound: str | None = Query(None)) -> list[StudyInfo]:
    """Return studies, optionally filtered by compound."""
    return discover_studies(PROJECTS_BASE_PATH, compound)


@router.get("/studies/search", response_model=list[StudyInfo])
async def search(q: str = Query("", min_length=1)) -> list[StudyInfo]:
    """Fuzzy-search compounds / studies by keyword."""
    return search_studies(PROJECTS_BASE_PATH, q)


class RefreshResult(BaseModel):
    message: str


@router.post("/cache/refresh", response_model=RefreshResult)
async def refresh_cache() -> RefreshResult:
    """Clear the directory scan cache and tracker parse cache.

    After this call the next request will re-scan the filesystem and
    pick up newly added / removed studies and tracker files.
    """
    study_dir_cache.invalidate()
    tracker_cache.invalidate()
    return RefreshResult(message="缓存已刷新，新的项目和文件变动将在下次请求时生效")
