"""Service for filtering and aggregating TaskItems."""

from __future__ import annotations

from datetime import date

from models import DashboardFilter, DashboardResponse, StatusSummary, TaskItem

_TIME_RANGE_DAYS: dict[str, tuple[int, int | None]] = {
    "3d": (0, 3),
    "5d": (0, 5),
    "10d": (0, 10),
    "15d": (0, 15),
    "15d+": (15, None),
}


def _matches_person(task: TaskItem, name: str, role: str) -> bool:
    """Check whether *task* involves *name* on the specified role side (exact, case-insensitive)."""
    lower = name.strip().lower()
    if role in ("main", "all"):
        if task.main_person and task.main_person.strip().lower() == lower:
            return True
    if role in ("qc", "all"):
        if task.qc_person and task.qc_person.strip().lower() == lower:
            return True
    return False


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
    role: str = "all",
) -> StatusSummary:
    """Compute aggregated status counts with role-aware logic.

    - **进行中**: the relevant side has no status filled (null/empty)
    - **已完成, 可QC**: main_status == "已完成，可以QC"
    - **有问题 / 待定 / 已关闭**: derived from qc_status
    """
    summary = StatusSummary(total=len(tasks))
    for t in tasks:
        if role == "main":
            side_status = t.main_status
        elif role == "qc":
            side_status = t.qc_status
        else:
            side_status = t.main_status or t.qc_status

        if not side_status:
            summary.in_progress += 1
            continue

        main_key = _STATUS_MAP.get(side_status or "")
        if main_key == "completed_ready_qc":
            summary.completed_ready_qc += 1

        if main_key == "in_progress":
            summary.in_progress += 1

        qc_key = _STATUS_MAP.get(t.qc_status or "")
        if qc_key == "has_issues":
            summary.has_issues += 1
        elif qc_key == "pending":
            summary.pending += 1
        elif qc_key == "closed":
            summary.closed += 1

    return summary


def collect_persons(tasks: list[TaskItem]) -> list[str]:
    """Return a sorted, deduplicated list of all person names."""
    names: set[str] = set()
    for t in tasks:
        if t.main_person:
            names.add(t.main_person.strip())
        if t.qc_person:
            names.add(t.qc_person.strip())
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
