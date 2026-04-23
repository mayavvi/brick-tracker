"""Pydantic models for the tracker visualization platform."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Status enum
# ---------------------------------------------------------------------------

class TaskStatus(str, Enum):
    """Possible status values from the codelist sheet."""

    IN_PROGRESS = "进行中"
    COMPLETED_READY_QC = "已完成，可以QC"
    HAS_ISSUES = "有问题，请修改"
    PENDING = "待定，请留意"
    CLOSED = "关闭问题"
    UNKNOWN = ""


# ---------------------------------------------------------------------------
# Tracker file metadata
# ---------------------------------------------------------------------------

class TrackerFileInfo(BaseModel):
    """Metadata about a single tracker Excel file."""

    file_path: str
    file_name: str
    task_purpose: str  # extracted from filename, e.g. "dryrun", "ALL", "CSR"
    study_id: str
    compound: str
    last_modified: float  # epoch timestamp for cache invalidation


# ---------------------------------------------------------------------------
# Core task item
# ---------------------------------------------------------------------------

class TaskItem(BaseModel):
    """A single row parsed from a tracker sheet."""

    study_id: str
    compound: str
    task_purpose: str
    sheet_type: str  # "SPEC" | "数据集" | "TFLs"
    category: str | None = None  # SDTM / ADaM / TFLs类型
    item_name: str = ""

    # Main side
    main_program: str | None = None
    main_date: date | None = None
    main_person: str | None = None
    main_status: str | None = None

    # QC side
    qc_program: str | None = None
    qc_date: date | None = None
    qc_person: str | None = None
    qc_content: str | None = None
    qc_status: str | None = None

    # Additional
    ddl: date | None = None
    batch: str | None = None
    comment: str | None = None


# ---------------------------------------------------------------------------
# Study info
# ---------------------------------------------------------------------------

class StudyInfo(BaseModel):
    """Summary of a single study directory."""

    compound: str
    study_id: str
    tracker_files: list[TrackerFileInfo] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Dashboard request / response
# ---------------------------------------------------------------------------

class DashboardFilter(BaseModel):
    """Filters submitted by the user."""

    study_ids: list[str] = Field(default_factory=list)
    tracker_file_paths: list[str] = Field(default_factory=list)
    person_name: str | None = None
    time_range: Literal["3d", "5d", "10d", "15d", "15d+"] | None = None
    role: Literal["main", "qc", "all"] = "all"


class StatusSummary(BaseModel):
    """Aggregated count of tasks by status."""

    total: int = 0
    in_progress: int = 0
    completed_ready_qc: int = 0
    has_issues: int = 0
    pending: int = 0
    closed: int = 0
    not_started: int = 0


class DashboardResponse(BaseModel):
    """Full dashboard payload returned to the frontend."""

    summary: StatusSummary
    tasks: list[TaskItem]
    persons: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Custom tasks
# ---------------------------------------------------------------------------

class CustomTaskCreate(BaseModel):
    """Payload for creating / updating a custom task."""

    study_id: str
    task_name: str
    description: str = ""

    main_person: str = ""
    main_status: str = ""
    qc_person: str = ""
    qc_status: str = ""

    ddl: date | None = None
    tags: list[str] = Field(default_factory=list)


class CustomTask(CustomTaskCreate):
    """A user-defined non-tracker task with generated metadata."""

    id: str
    owner: str = ""
    created_at: str  # ISO datetime string


# ---------------------------------------------------------------------------
# User preferences
# ---------------------------------------------------------------------------

class UserPreferences(BaseModel):
    """Persisted user preferences for session restore."""

    selected_studies: list[str] = Field(default_factory=list)
    selected_tracker_files: dict[str, list[str]] = Field(default_factory=dict)
    person_filter: str = ""
    role_filter: str = "all"
    time_range: str = ""
    search_query: str = ""
    theme: str = "light"       # "light" | "dark"
    show_charts: bool = True   # whether the chart panel is expanded


class UserInfo(BaseModel):
    """Public user info returned to the frontend."""

    username: str
    display_name: str = ""


class WorkstationPrefs(BaseModel):
    """Workstation-specific preferences (aliases + watched studies)."""

    tracker_aliases: list[str] = Field(default_factory=list)
    watched_studies: list[str] = Field(default_factory=list)


class TodoItem(BaseModel):
    """Normalised todo entry — either from tracker (read-only) or custom (editable)."""

    key: str                          # "custom:<id>" | "tracker:<study>:<hash>"
    source: Literal["custom", "tracker"]
    title: str
    study_id: str
    role: Literal["main", "qc"] = "main"
    status: str = ""
    person: str | None = None
    ddl: date | None = None
    editable: bool = True


# ---------------------------------------------------------------------------
# File compare (P1)
# ---------------------------------------------------------------------------

class FileEntry(BaseModel):
    """Indexed program/log file metadata for file-compare module."""

    abs_path: str
    rel_path: str
    study_id: str
    task: str
    role: Literal["main", "qc", "unknown"]
    kind: Literal["sas", "log", "lst", "other"]
    size: int
    mtime: float


class FileSnapshot(BaseModel):
    """Snapshot metadata for one version of a file."""

    id: int
    username: str
    abs_path: str
    content_hash: str
    size_bytes: int
    note: str = ""
    snapshot_ts: datetime


class IndexedFile(BaseModel):
    """One globally indexed file record."""

    id: int
    full_path: str
    rel_path: str
    compound: str
    project: str
    task: str
    file_name: str
    program_key: str
    extension: str
    role: Literal["main", "qc", "unknown"]
    modified_time: datetime
    size: int
    content_hash: str


class ProgramGroup(BaseModel):
    """Aggregated program listing row for the workbench."""

    program_key: str
    extension: str
    display_name: str
    version_count: int
    latest_modified_time: datetime
    tasks: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    compounds: list[str] = Field(default_factory=list)


class ProgramVersion(IndexedFile):
    """Concrete indexed version row used in timelines and comparisons."""


class CodeIndexContext(BaseModel):
    """Distinct filter values available in the indexed workbench."""

    compounds: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    tasks: list[str] = Field(default_factory=list)
    extensions: list[str] = Field(default_factory=list)


class CodeIndexFilterOptions(BaseModel):
    """Cascading filter options for compound / project / task pickers."""

    projects: list[str] = Field(default_factory=list)
    tasks: list[str] = Field(default_factory=list)


class CodeIndexStatus(BaseModel):
    """Top-level status summary for the code index."""

    indexed_files: int = 0
    program_groups: int = 0
    last_indexed_at: datetime | None = None


class DiffLine(BaseModel):
    """One row in a structured diff view."""

    op: Literal["equal", "insert", "delete", "replace"]
    a_lineno: int | None
    b_lineno: int | None
    a_text: str = ""
    b_text: str = ""


class UnifiedDiffLine(BaseModel):
    """One row in a unified diff view with real source line numbers."""

    kind: Literal["hunk", "context", "insert", "delete"]
    a_lineno: int | None
    b_lineno: int | None
    text: str


class QcTimingRow(BaseModel):
    """QC timing check row for one (task, program)."""

    task: str
    program: str
    main_log_mtime: datetime | None = None
    qc_log_mtime: datetime | None = None
    stale: bool
    reason: Literal["qc-older", "qc-missing", "ok"]
    main_log_path: str | None = None
    qc_log_path: str | None = None
    main_sas_path: str | None = None
    qc_sas_path: str | None = None
