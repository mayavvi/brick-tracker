"""API routes for the aggregated dashboard view."""

from __future__ import annotations

from fastapi import APIRouter, Query

from config import PROJECTS_BASE_PATH
from models import DashboardFilter, DashboardResponse, TaskItem
from services.cache import tracker_cache
from services.filter import build_dashboard, collect_persons
from services.scanner import discover_studies

router = APIRouter(prefix="/api", tags=["dashboard"])


def _load_tasks_for_studies(
    study_ids: list[str],
    tracker_file_paths: list[str] | None = None,
) -> list[TaskItem]:
    """Load and cache-parse tasks, optionally filtered by file paths."""
    all_studies = discover_studies(PROJECTS_BASE_PATH)
    id_set = set(study_ids)
    path_set = set(tracker_file_paths) if tracker_file_paths else None
    tasks: list[TaskItem] = []
    for study in all_studies:
        if study.study_id not in id_set:
            continue
        for tracker_file in study.tracker_files:
            if path_set and tracker_file.file_path not in path_set:
                continue
            tasks.extend(tracker_cache.get_tasks(tracker_file))
    return tasks


@router.post("/dashboard", response_model=DashboardResponse)
def dashboard(filters: DashboardFilter) -> DashboardResponse:
    """Return filtered and summarised dashboard data."""
    tasks = _load_tasks_for_studies(
        filters.study_ids,
        filters.tracker_file_paths or None,
    )
    return build_dashboard(tasks, filters)


@router.get("/persons", response_model=list[str])
def list_persons(
    study_ids: list[str] = Query(default=[]),
) -> list[str]:
    """Return all person names found in the given studies."""
    if not study_ids:
        return []
    tasks = _load_tasks_for_studies(study_ids)
    return collect_persons(tasks)
