"""Snapshot persistence helpers for file-compare module."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from config import PROJECTS_BASE_PATH
from database import get_db
from services.file_reader import decode_bytes, resolve_safe_path, sha256_bytes


def _extract_study_id(path: Path) -> str:
    try:
        rel = path.relative_to(PROJECTS_BASE_PATH)
    except Exception:
        return ""
    parts = rel.parts
    if len(parts) >= 2:
        return parts[1]
    return ""


async def create_snapshot(
    username: str,
    path: str,
    note: str = "",
    max_bytes: int = 5_000_000,
) -> dict[str, Any]:
    """Create a file snapshot (or dedupe to latest one with same hash)."""
    p = resolve_safe_path(path).resolve(strict=True)
    if not p.is_file():
        raise FileNotFoundError(str(p))

    raw = p.read_bytes()
    size_bytes = len(raw)
    if size_bytes > max_bytes:
        raise ValueError(f"文件过大（{size_bytes} bytes），暂不支持快照")

    content_hash = sha256_bytes(raw)
    content, encoding, _ = decode_bytes(raw, max_bytes=None)
    abs_path = str(p)

    db = await get_db()
    latest_rows = await db.execute_fetchall(
        """
        SELECT id, username, abs_path, content_hash, size_bytes, note, snapshot_ts
        FROM file_snapshots
        WHERE username = ? AND abs_path = ?
        ORDER BY snapshot_ts DESC, id DESC
        LIMIT 1
        """,
        (username, abs_path),
    )
    if latest_rows and latest_rows[0]["content_hash"] == content_hash:
        row = dict(latest_rows[0])
        row["deduplicated"] = True
        return row

    now = datetime.now().isoformat(timespec="seconds")
    cur = await db.execute(
        """
        INSERT INTO file_snapshots
            (username, abs_path, study_id, content_hash, content, encoding, size_bytes, note, snapshot_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            username,
            abs_path,
            _extract_study_id(p),
            content_hash,
            content,
            encoding,
            size_bytes,
            note.strip(),
            now,
        ),
    )
    await db.commit()
    row = {
        "id": cur.lastrowid,
        "username": username,
        "abs_path": abs_path,
        "content_hash": content_hash,
        "size_bytes": size_bytes,
        "note": note.strip(),
        "snapshot_ts": now,
        "deduplicated": False,
    }
    return row


async def list_snapshots(username: str, path: str) -> list[dict[str, Any]]:
    """List snapshots for one file path, newest first."""
    p = resolve_safe_path(path).resolve(strict=False)
    db = await get_db()
    rows = await db.execute_fetchall(
        """
        SELECT id, username, abs_path, content_hash, size_bytes, note, snapshot_ts
        FROM file_snapshots
        WHERE username = ? AND abs_path = ?
        ORDER BY snapshot_ts DESC, id DESC
        """,
        (username, str(p)),
    )
    return [dict(r) for r in rows]


async def get_snapshot(username: str, snap_id: int) -> dict[str, Any] | None:
    """Fetch one snapshot with content, scoped to username."""
    db = await get_db()
    rows = await db.execute_fetchall(
        """
        SELECT id, username, abs_path, content_hash, content, encoding, size_bytes, note, snapshot_ts
        FROM file_snapshots
        WHERE id = ? AND username = ?
        LIMIT 1
        """,
        (snap_id, username),
    )
    if not rows:
        return None
    return dict(rows[0])
