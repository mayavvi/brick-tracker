"""API routes for parsing tracker files."""

from __future__ import annotations

from fastapi import APIRouter, Body

from config import PROJECTS_BASE_PATH
from models import TaskItem
from services.cache import tracker_cache
from services.scanner import discover_studies

router = APIRouter(prefix="/api/tracker", tags=["tracker"])


@router.post("/parse", response_model=list[TaskItem])
def parse_trackers(
    study_ids: list[str] = Body(..., embed=True),
) -> list[TaskItem]:
    """Parse tracker files for the given study IDs and return all tasks."""
    all_studies = discover_studies(PROJECTS_BASE_PATH)
    id_set = set(study_ids)

    tasks: list[TaskItem] = []
    for study in all_studies:
        if study.study_id not in id_set:
            continue
        for tracker_file in study.tracker_files:
            tasks.extend(tracker_cache.get_tasks(tracker_file))
    return tasks
