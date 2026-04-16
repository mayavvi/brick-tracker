"""Pydantic models for the tracker visualization platform."""

from __future__ import annotations

from datetime import date
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


class UserInfo(BaseModel):
    """Public user info returned to the frontend."""

    username: str
    display_name: str = ""
