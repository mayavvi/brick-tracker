"""Build a unified, time-sorted todo list from tracker + custom tasks."""

from __future__ import annotations

from datetime import date, datetime

from config import PROJECTS_BASE_PATH
from database import get_preferences
from models import TaskStatus, TodoItem
from services.cache import tracker_cache
from services.custom_tasks import custom_task_store
from services.scanner import discover_studies

_DONE = {TaskStatus.COMPLETED_READY_QC.value, TaskStatus.CLOSED.value}


def _to_date(v: object) -> date | None:
    if v is None:
        return None
    if isinstance(v, date):
        return v
    try:
        return datetime.strptime(str(v), "%Y-%m-%d").date()
    except Exception:
        return None


async def build_my_todos(username: str, display_name: str = "") -> list[TodoItem]:
    prefs = await get_preferences(username)
    aliases: list[str] = prefs.get("tracker_aliases", [])
    watched: list[str] = prefs.get("watched_studies", [])

    if not aliases:
        aliases = [a for a in [username, display_name] if a]

    alias_set = {a.strip().lower() for a in aliases if a.strip()}
    todos: list[TodoItem] = []

    # --- Tracker tasks (read-only) ---
    if watched and alias_set:
        id_set = set(watched)
        for study in discover_studies(PROJECTS_BASE_PATH):
            if study.study_id not in id_set:
                continue
            for tracker_file in study.tracker_files:
                for task in tracker_cache.get_tasks(tracker_file):
                    mp = (task.main_person or "").strip().lower()
                    qp = (task.qc_person or "").strip().lower()
                    if mp in alias_set and task.main_status not in _DONE:
                        todos.append(TodoItem(
                            key=f"tracker:{task.study_id}:{task.item_name}:{task.category}:main",
                            source="tracker",
                            title=task.item_name or task.main_program or "未命名",
                            study_id=task.study_id,
                            role="main",
                            status=task.main_status or "",
                            person=task.main_person,
                            ddl=_to_date(task.ddl),
                            editable=False,
                        ))
                    if qp in alias_set and task.qc_status not in _DONE:
                        todos.append(TodoItem(
                            key=f"tracker:{task.study_id}:{task.item_name}:{task.category}:qc",
                            source="tracker",
                            title=task.item_name or task.qc_program or "未命名",
                            study_id=task.study_id,
                            role="qc",
                            status=task.qc_status or "",
                            person=task.qc_person,
                            ddl=_to_date(task.ddl),
                            editable=False,
                        ))

    # --- Custom tasks (editable) ---
    for ct in await custom_task_store.list_all(username):
        if ct.main_status in _DONE:
            continue
        todos.append(TodoItem(
            key=f"custom:{ct.id}",
            source="custom",
            title=ct.task_name,
            study_id=ct.study_id,
            role="main",
            status=ct.main_status or "",
            person=ct.main_person or None,
            ddl=_to_date(ct.ddl),
            editable=True,
        ))

    todos.sort(key=lambda t: (0, t.ddl) if t.ddl else (1, date.max))
    return todos
