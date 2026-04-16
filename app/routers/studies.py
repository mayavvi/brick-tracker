"""API routes for compound / study discovery."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.config import PROJECTS_BASE_PATH
from app.models import StudyInfo
from app.services.scanner import discover_compounds, discover_studies, search_studies

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
