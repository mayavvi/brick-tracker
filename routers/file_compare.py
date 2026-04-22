"""API routes for file preview/search/tree (P1)."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth import User, get_current_user
from models import FileEntry, FileSnapshot
from services.file_diff import diff_texts, summarize
from services.file_index import get_tree, search
from services.file_reader import read_text, read_text_full, resolve_safe_path, to_rel_path
from services.file_snapshots import create_snapshot, get_snapshot, list_snapshots

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/files", tags=["files"])


class SnapshotCreatePayload(BaseModel):
    path: str = Field(..., min_length=1)
    note: str = ""


@router.get("/tree")
def file_tree(
    study_id: str = Query(..., min_length=1),
    user: User = Depends(get_current_user),
) -> dict:
    """Return task/folder/file tree for one study."""
    _ = user
    try:
        return get_tree(study_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Study 不存在")
    except Exception:
        logger.exception("Failed to build file tree for study=%s", study_id)
        raise HTTPException(status_code=500, detail="构建文件树失败")


@router.get("/search", response_model=list[FileEntry])
def file_search(
    q: str = Query("", min_length=0),
    study_id: str | None = Query(None),
    kind: Literal["sas", "log", "lst", "other"] | None = Query(None),
    role: Literal["main", "qc", "unknown"] | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    user: User = Depends(get_current_user),
) -> list[FileEntry]:
    """Search files by name/path with optional filters."""
    _ = user
    try:
        return search(q, study_id=study_id, kind=kind, role=role, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Study 不存在")
    except Exception:
        logger.exception(
            "File search failed: q=%r study=%r kind=%r role=%r",
            q, study_id, kind, role,
        )
        raise HTTPException(status_code=500, detail="文件搜索失败")


@router.get("/preview")
def file_preview(
    path: str = Query(..., min_length=1),
    max_bytes: int = Query(2_000_000, ge=1024, le=10_000_000),
    user: User = Depends(get_current_user),
) -> dict:
    """Preview file content in read-only mode using Path.read_bytes()."""
    _ = user
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
        raise HTTPException(status_code=403, detail="路径不在允许范围内")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="文件不存在")
    except IsADirectoryError:
        raise HTTPException(status_code=400, detail="目标是目录，不是文件")
    except Exception:
        logger.exception("File preview failed for path=%r", path)
        raise HTTPException(status_code=500, detail="文件预览失败")


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
        raise HTTPException(status_code=403, detail="路径不在允许范围内")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="文件不存在")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("Snapshot create failed: path=%r", payload.path)
        raise HTTPException(status_code=500, detail="创建快照失败")


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
        raise HTTPException(status_code=403, detail="路径不在允许范围内")
    except Exception:
        logger.exception("Snapshot list failed: path=%r", path)
        raise HTTPException(status_code=500, detail="读取快照历史失败")


@router.get("/diff")
async def file_diff(
    a_snap_id: int | None = Query(None, ge=1),
    a_path: str | None = Query(None),
    b_snap_id: int | None = Query(None, ge=1),
    b_path: str | None = Query(None),
    ignore_whitespace: bool = Query(False),
    ignore_case: bool = Query(False),
    user: User = Depends(get_current_user),
) -> dict:
    """Diff endpoint: each side can be snapshot or current file."""
    if a_snap_id is None and a_path is None:
        raise HTTPException(status_code=400, detail="缺少 A 侧输入（a_snap_id 或 a_path）")
    if b_snap_id is None and b_path is None:
        raise HTTPException(status_code=400, detail="缺少 B 侧输入（b_snap_id 或 b_path）")

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

        lines = diff_texts(
            a_text,
            b_text,
            ignore_whitespace=ignore_whitespace,
            ignore_case=ignore_case,
        )
        return {
            "summary": summarize(lines),
            "a_label": a_label,
            "b_label": b_label,
            "a_path": a_abs_path,
            "b_path": b_abs_path,
            "lines": [line.model_dump() for line in lines],
        }
    except PermissionError:
        raise HTTPException(status_code=403, detail="路径不在允许范围内")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="文件不存在")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception(
            "Diff failed: a_snap_id=%r a_path=%r b_snap_id=%r b_path=%r",
            a_snap_id, a_path, b_snap_id, b_path,
        )
        raise HTTPException(status_code=500, detail="文件比对失败")


async def _resolve_diff_side(
    username: str,
    snap_id: int | None,
    path: str | None,
) -> tuple[str, str, str]:
    if snap_id is not None:
        snap = await get_snapshot(username, snap_id)
        if not snap:
            raise ValueError(f"快照不存在或无权限: {snap_id}")
        return (
            snap["content"],
            f"快照 #{snap['id']} · {snap['snapshot_ts']}",
            snap["abs_path"],
        )

    if not path:
        raise ValueError("缺少路径输入")
    p = resolve_safe_path(path)
    text, _, _ = read_text_full(p)
    return text, f"当前文件 · {p.name}", str(p)
