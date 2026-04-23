"""API routes for file preview, snapshots, diff, and indexed code workbench."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth import User, get_current_user
from models import (
    CodeIndexContext,
    CodeIndexStatus,
    FileEntry,
    FileSnapshot,
    ProgramGroup,
    ProgramVersion,
    QcTimingRow,
)
from services import code_index
from services.file_diff import diff_both, summarize
from services.file_index import get_tree, search
from services.file_reader import read_text, read_text_full, resolve_safe_path, to_rel_path
from services.file_snapshots import create_snapshot, get_snapshot, list_snapshots
from services.qc_timing import check_study

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/files", tags=["files"])


class SnapshotCreatePayload(BaseModel):
    path: str = Field(..., min_length=1)
    note: str = ""


class CodeIndexRebuildResponse(BaseModel):
    indexed_files: int
    last_indexed_at: str


@router.get("/tree")
def file_tree(
    study_id: str = Query(..., min_length=1),
    _: User = Depends(get_current_user),
) -> dict:
    """Return task/folder/file tree for one study."""
    try:
        return get_tree(study_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Study not found")
    except Exception:
        logger.exception("Failed to build file tree for study=%s", study_id)
        raise HTTPException(status_code=500, detail="Failed to build file tree")


@router.get("/search", response_model=list[FileEntry])
def file_search(
    q: str = Query("", min_length=0),
    study_id: str | None = Query(None),
    kind: Literal["sas", "log", "lst", "other"] | None = Query(None),
    role: Literal["main", "qc", "unknown"] | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    _: User = Depends(get_current_user),
) -> list[FileEntry]:
    """Search files by name/path with optional filters."""
    try:
        return search(q, study_id=study_id, kind=kind, role=role, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Study not found")
    except Exception:
        logger.exception(
            "File search failed: q=%r study=%r kind=%r role=%r",
            q,
            study_id,
            kind,
            role,
        )
        raise HTTPException(status_code=500, detail="File search failed")


@router.get("/preview")
def file_preview(
    path: str = Query(..., min_length=1),
    max_bytes: int = Query(2_000_000, ge=1024, le=10_000_000),
    _: User = Depends(get_current_user),
) -> dict:
    """Preview file content in read-only mode using Path.read_bytes()."""
    try:
        p = resolve_safe_path(path)
        text, encoding, truncated, size_bytes = read_text(p, max_bytes=max_bytes)
        return {
            "abs_path": str(p),
            "rel_path": to_rel_path(p),
            "text": text,
            "encoding": encoding,
            "size_bytes": size_bytes,
            "truncated": truncated,
            "line_count": text.count("\n") + (1 if text else 0),
        }
    except PermissionError:
        raise HTTPException(status_code=403, detail="Path is outside the allowed base directory")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    except IsADirectoryError:
        raise HTTPException(status_code=400, detail="Target is a directory, not a file")
    except Exception:
        logger.exception("File preview failed for path=%r", path)
        raise HTTPException(status_code=500, detail="File preview failed")


@router.post("/snapshot")
async def snapshot_create(
    payload: SnapshotCreatePayload,
    user: User = Depends(get_current_user),
) -> dict:
    """Create one snapshot for current file content."""
    try:
        return await create_snapshot(
            username=user.username,
            path=payload.path,
            note=payload.note,
        )
    except PermissionError:
        raise HTTPException(status_code=403, detail="Path is outside the allowed base directory")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("Snapshot create failed: path=%r", payload.path)
        raise HTTPException(status_code=500, detail="Snapshot creation failed")


@router.get("/snapshots", response_model=list[FileSnapshot])
async def snapshot_list(
    path: str = Query(..., min_length=1),
    user: User = Depends(get_current_user),
) -> list[FileSnapshot]:
    """List all snapshots for one file."""
    try:
        rows = await list_snapshots(user.username, path)
        return [FileSnapshot(**row) for row in rows]
    except PermissionError:
        raise HTTPException(status_code=403, detail="Path is outside the allowed base directory")
    except Exception:
        logger.exception("Snapshot list failed: path=%r", path)
        raise HTTPException(status_code=500, detail="Snapshot history failed")


@router.get("/diff")
async def file_diff(
    a_snap_id: int | None = Query(None, ge=1),
    a_path: str | None = Query(None),
    b_snap_id: int | None = Query(None, ge=1),
    b_path: str | None = Query(None),
    ignore_whitespace: bool = Query(False),
    ignore_case: bool = Query(False),
    mode: Literal["side-by-side", "unified"] = Query("side-by-side"),
    user: User = Depends(get_current_user),
) -> dict:
    """Legacy diff endpoint: each side can be snapshot or current file."""
    if a_snap_id is None and a_path is None:
        raise HTTPException(status_code=400, detail="Missing A-side input")
    if b_snap_id is None and b_path is None:
        raise HTTPException(status_code=400, detail="Missing B-side input")

    try:
        a_text, a_label, a_abs_path = await _resolve_diff_side(
            user.username,
            snap_id=a_snap_id,
            path=a_path,
        )
        b_text, b_label, b_abs_path = await _resolve_diff_side(
            user.username,
            snap_id=b_snap_id,
            path=b_path,
        )

        lines, unified_lines = diff_both(
            a_text,
            b_text,
            ignore_whitespace=ignore_whitespace,
            ignore_case=ignore_case,
            want_unified=True,
        )
        return {
            "mode": mode,
            "summary": summarize(lines),
            "a_label": a_label,
            "b_label": b_label,
            "a_path": a_abs_path,
            "b_path": b_abs_path,
            "lines": [line.model_dump() for line in lines],
            "unified_lines": [line.model_dump() for line in unified_lines],
        }
    except PermissionError:
        raise HTTPException(status_code=403, detail="Path is outside the allowed base directory")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception(
            "Diff failed: a_snap_id=%r a_path=%r b_snap_id=%r b_path=%r mode=%s",
            a_snap_id,
            a_path,
            b_snap_id,
            b_path,
            mode,
        )
        raise HTTPException(status_code=500, detail="File diff failed")


@router.get("/qc-timing", response_model=list[QcTimingRow])
def qc_timing(
    study_id: str = Query(..., min_length=1),
    _: User = Depends(get_current_user),
) -> list[QcTimingRow]:
    """Legacy main-vs-QC log recency check for one study."""
    try:
        return check_study(study_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Study not found")
    except Exception:
        logger.exception("QC timing check failed: study=%s", study_id)
        raise HTTPException(status_code=500, detail="QC timing check failed")


@router.get("/status", response_model=CodeIndexStatus)
async def code_index_status(_: User = Depends(get_current_user)) -> CodeIndexStatus:
    """Return index status for the indexed workbench."""
    try:
        return await code_index.ensure_index()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        logger.exception("Failed to load code index status")
        raise HTTPException(status_code=500, detail="Code index status failed")


@router.post("/reindex", response_model=CodeIndexRebuildResponse)
async def code_index_rebuild(_: User = Depends(get_current_user)) -> CodeIndexRebuildResponse:
    """Rebuild the global code index."""
    try:
        return CodeIndexRebuildResponse(**await code_index.rebuild_index())
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        logger.exception("Failed to rebuild code index")
        raise HTTPException(status_code=500, detail="Code index rebuild failed")


@router.get("/contexts", response_model=CodeIndexContext)
async def code_index_contexts(_: User = Depends(get_current_user)) -> CodeIndexContext:
    """Return distinct filter values for indexed queries."""
    try:
        return await code_index.get_contexts()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        logger.exception("Failed to load code index contexts")
        raise HTTPException(status_code=500, detail="Code index contexts failed")


@router.get("/programs", response_model=list[ProgramGroup])
async def code_index_programs(
    search: str = Query("", min_length=0),
    compound: str | None = Query(None),
    project: str | None = Query(None),
    task: str | None = Query(None),
    extension: str | None = Query(None),
    role: str | None = Query(None),
    limit: int = Query(200, ge=1, le=500),
    _: User = Depends(get_current_user),
) -> list[ProgramGroup]:
    """Return aggregated program rows for the workbench."""
    try:
        return await code_index.query_program_groups(
            search=search,
            compound=compound,
            project=project,
            task=task,
            extension=extension,
            role=role,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        logger.exception(
            "Failed to query code index programs: search=%r compound=%r project=%r task=%r extension=%r role=%r",
            search,
            compound,
            project,
            task,
            extension,
            role,
        )
        raise HTTPException(status_code=500, detail="Code index program query failed")


@router.get("/timeline", response_model=list[ProgramVersion])
async def code_index_timeline(
    program_key: str = Query(..., min_length=1),
    extension: str | None = Query(None),
    compound: str | None = Query(None),
    project: str | None = Query(None),
    task: str | None = Query(None),
    role: str | None = Query(None),
    _: User = Depends(get_current_user),
) -> list[ProgramVersion]:
    """Return all indexed versions for one program."""
    try:
        return await code_index.get_program_timeline(
            program_key=program_key,
            extension=extension,
            compound=compound,
            project=project,
            task=task,
            role=role,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        logger.exception(
            "Failed to load timeline for program=%r extension=%r",
            program_key,
            extension,
        )
        raise HTTPException(status_code=500, detail="Code index timeline failed")


@router.get("/indexed-preview/{file_id}")
async def code_index_preview(
    file_id: int,
    max_bytes: int = Query(2_000_000, ge=1024, le=10_000_000),
    _: User = Depends(get_current_user),
) -> dict:
    """Preview one indexed file by id."""
    try:
        return await code_index.preview_indexed_file(file_id, max_bytes=max_bytes)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError:
        raise HTTPException(status_code=403, detail="Path is outside the allowed base directory")
    except Exception:
        logger.exception("Failed to preview indexed file id=%s", file_id)
        raise HTTPException(status_code=500, detail="Indexed preview failed")


@router.get("/indexed-diff")
async def code_index_diff(
    a_file_id: int | None = Query(None, ge=1),
    a_snap_id: int | None = Query(None, ge=1),
    a_path: str | None = Query(None),
    b_file_id: int | None = Query(None, ge=1),
    b_snap_id: int | None = Query(None, ge=1),
    b_path: str | None = Query(None),
    ignore_whitespace: bool = Query(False),
    ignore_case: bool = Query(False),
    mode: Literal["side-by-side", "unified"] = Query("side-by-side"),
    user: User = Depends(get_current_user),
) -> dict:
    """Diff endpoint that accepts indexed files, snapshots, or live paths."""
    if a_file_id is None and a_snap_id is None and a_path is None:
        raise HTTPException(status_code=400, detail="Missing A-side input")
    if b_file_id is None and b_snap_id is None and b_path is None:
        raise HTTPException(status_code=400, detail="Missing B-side input")

    try:
        a_text, a_label, a_abs_path = await _resolve_diff_side(
            user.username,
            indexed_file_id=a_file_id,
            snap_id=a_snap_id,
            path=a_path,
        )
        b_text, b_label, b_abs_path = await _resolve_diff_side(
            user.username,
            indexed_file_id=b_file_id,
            snap_id=b_snap_id,
            path=b_path,
        )

        lines, unified_lines = diff_both(
            a_text,
            b_text,
            ignore_whitespace=ignore_whitespace,
            ignore_case=ignore_case,
            want_unified=True,
        )
        return {
            "mode": mode,
            "summary": summarize(lines),
            "a_label": a_label,
            "b_label": b_label,
            "a_path": a_abs_path,
            "b_path": b_abs_path,
            "lines": [line.model_dump() for line in lines],
            "unified_lines": [line.model_dump() for line in unified_lines],
        }
    except PermissionError:
        raise HTTPException(status_code=403, detail="Path is outside the allowed base directory")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception(
            "Indexed diff failed: a_file_id=%r a_snap_id=%r a_path=%r b_file_id=%r b_snap_id=%r b_path=%r",
            a_file_id,
            a_snap_id,
            a_path,
            b_file_id,
            b_snap_id,
            b_path,
        )
        raise HTTPException(status_code=500, detail="Indexed diff failed")


@router.get("/indexed-qc-timing", response_model=list[QcTimingRow])
async def code_index_qc_timing(
    compound: str | None = Query(None),
    project: str | None = Query(None),
    task: str | None = Query(None),
    _: User = Depends(get_current_user),
) -> list[QcTimingRow]:
    """QC timing view backed by the global index."""
    try:
        return await code_index.get_qc_timing_rows(
            compound=compound,
            project=project,
            task=task,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        logger.exception(
            "Indexed QC timing failed: compound=%r project=%r task=%r",
            compound,
            project,
            task,
        )
        raise HTTPException(status_code=500, detail="Indexed QC timing failed")


async def _resolve_diff_side(
    username: str,
    indexed_file_id: int | None = None,
    snap_id: int | None = None,
    path: str | None = None,
) -> tuple[str, str, str]:
    if indexed_file_id is not None:
        return await code_index.resolve_indexed_diff_target(indexed_file_id)

    if snap_id is not None:
        snap = await get_snapshot(username, snap_id)
        if not snap:
            raise ValueError(f"Snapshot does not exist or is not accessible: {snap_id}")
        return (
            snap["content"],
            f"Snapshot #{snap['id']} | {snap['snapshot_ts']}",
            snap["abs_path"],
        )

    if not path:
        raise ValueError("Missing path input")
    p = resolve_safe_path(path)
    text, _, _ = read_text_full(p)
    return text, f"Live file | {p.name}", str(p)
