"""Service for filtering and aggregating TaskItems."""

from __future__ import annotations

import re
from datetime import date

from models import DashboardFilter, DashboardResponse, StatusSummary, TaskItem

_PERSON_SEPARATORS = re.compile(r"[/,，、;；]+")


def _split_person_tokens(value: str | None) -> list[str]:
    if not value:
        return []
    return [tok.strip() for tok in _PERSON_SEPARATORS.split(value) if tok.strip()]

_TIME_RANGE_DAYS: dict[str, tuple[int, int | None]] = {
    "3d": (0, 3),
    "5d": (0, 5),
    "10d": (0, 10),
    "15d": (0, 15),
    "15d+": (15, None),
}


def _matches_person(task: TaskItem, name: str, role: str) -> bool:
    """Check whether *task* involves *name* on the role side.

    Splits the stored person field on common separators (`/`, `,`, `，`, `、`, `;`,
    `；`) so handover values like ``"A/B"`` match a query of ``"B"``. Matching is
    case-insensitive; if no token equals the query exactly, falls back to a
    substring check so partial typing still narrows the list.
    """
    query = name.strip().lower()
    if not query:
        return False
    field = task.main_person if role == "main" else task.qc_person if role == "qc" else None
    if not field:
        return False
    tokens = [tok.lower() for tok in _split_person_tokens(field)]
    if any(tok == query for tok in tokens):
        return True
    return any(query in tok for tok in tokens)


def _ddl_in_range(
    task: TaskItem,
    today: date,
    lo_days: int,
    hi_days: int | None,
) -> bool:
    """Check if the task DDL falls within [today+lo, today+hi)."""
    if task.ddl is None:
        return False
    delta = (task.ddl - today).days
    if delta < lo_days:
        return False
    if hi_days is not None and delta >= hi_days:
        return False
    return True


def filter_tasks(
    tasks: list[TaskItem],
    filters: DashboardFilter,
) -> list[TaskItem]:
    """Apply dashboard filters to a list of tasks."""
    result = tasks

    if filters.study_ids:
        id_set = set(filters.study_ids)
        result = [t for t in result if t.study_id in id_set]

    if filters.person_name:
        result = [
            t for t in result
            if _matches_person(t, filters.person_name, filters.role)
        ]

    if filters.time_range and filters.time_range in _TIME_RANGE_DAYS:
        lo, hi = _TIME_RANGE_DAYS[filters.time_range]
        today = date.today()
        result = [t for t in result if _ddl_in_range(t, today, lo, hi)]

    return result


_STATUS_MAP = {
    "进行中": "in_progress",
    "已完成，可以QC": "completed_ready_qc",
    "有问题，请修改": "has_issues",
    "待定，请留意": "pending",
    "关闭问题": "closed",
}


def build_summary(
    tasks: list[TaskItem],
    role: str = "main",
) -> StatusSummary:
    """Compute aggregated status counts with role-aware logic.

    - **进行中**: the relevant side has no status filled (null/empty) OR explicitly set to "进行中"
    - **已完成, 可QC**: main_status == "已完成，可以QC"
    - **有问题 / 待定 / 已关闭**: derived from qc_status
    """
    def _side_in_progress(status: str | None) -> bool:
        return not status or status == "进行中"

    summary = StatusSummary(total=len(tasks))
    for t in tasks:
        # --- in_progress: empty status OR explicitly "进行中" ---
        if role == "qc":
            is_in_progress = _side_in_progress(t.qc_status)
        else:
            is_in_progress = _side_in_progress(t.main_status)

        if is_in_progress:
            summary.in_progress += 1

        # --- main side ---
        main_key = _STATUS_MAP.get(t.main_status or "")
        if main_key == "completed_ready_qc":
            summary.completed_ready_qc += 1

        # --- qc side ---
        qc_key = _STATUS_MAP.get(t.qc_status or "")
        if qc_key == "has_issues":
            summary.has_issues += 1
        elif qc_key == "pending":
            summary.pending += 1
        elif qc_key == "closed":
            summary.closed += 1

    return summary


def collect_persons(tasks: list[TaskItem]) -> list[str]:
    """Return a sorted, deduplicated list of all person names.

    Handover values like ``"A/B"`` are split into individual tokens so the
    operator dropdown surfaces both A and B as separate suggestions.
    """
    names: set[str] = set()
    for t in tasks:
        for tok in _split_person_tokens(t.main_person):
            names.add(tok)
        for tok in _split_person_tokens(t.qc_person):
            names.add(tok)
    return sorted(names)


def build_dashboard(
    tasks: list[TaskItem],
    filters: DashboardFilter,
) -> DashboardResponse:
    """Full pipeline: filter -> summarise -> respond."""
    filtered = filter_tasks(tasks, filters)
    return DashboardResponse(
        summary=build_summary(filtered, role=filters.role),
        tasks=filtered,
        persons=collect_persons(filtered),
    )
