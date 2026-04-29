"""Global code index for preview, timeline, and compare workflows."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from config import DATABASE_PATH, PROJECTS_BASE_PATH
from database import get_db, init_db
from models import (
    CodeIndexContext,
    CodeIndexFilterOptions,
    CodeIndexStatus,
    IndexedFile,
    ProgramGroup,
    ProgramVersion,
    QcTimingRow,
)
from services.file_reader import read_text, read_text_full

logger = logging.getLogger(__name__)

TARGET_EXTENSIONS = {".sas", ".log"}
ROLE_ROOTS = {"prog", "qcprog", "data", "qcdata", "outputs"}

_SKIP_DIRS = {"archive", "documents", ".git", "__pycache__", ".svn"}

_INDEX_BOOTSTRAPPED = False
_REBUILD_LOCK = asyncio.Lock()
_INSERT_BATCH_SIZE = 500
_HASH_CHUNK_BYTES = 65_536
_HASH_WORKERS = 8


def _file_sha256_hex(path: Path) -> str:
    """Stream a file through SHA-256 without loading it fully into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(_HASH_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _walk_target_files(root: Path, extensions: set[str]) -> list[Path]:
    """Walk *root* using os.scandir, pruning irrelevant directories early."""
    result: list[Path] = []
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = os.scandir(current)
        except (PermissionError, OSError):
            continue
        with entries:
            for entry in entries:
                name_lower = entry.name.lower()
                if entry.is_dir(follow_symlinks=False):
                    if name_lower not in _SKIP_DIRS and "archive" not in name_lower:
                        stack.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    ext = os.path.splitext(name_lower)[1]
                    if ext in extensions and "temp" not in name_lower:
                        result.append(Path(entry.path))
    return result


def parse_index_entry(path: Path, base_path: Path | None = None) -> dict | None:
    """Return one normalized index row or ``None`` when the file should be skipped."""
    base = (base_path or PROJECTS_BASE_PATH).resolve()
    resolved = path.resolve(strict=False)
    if not resolved.is_file():
        return None
    if not resolved.is_relative_to(base):
        return None
    if resolved.suffix.lower() not in TARGET_EXTENSIONS:
        return None
    if "temp" in resolved.name.lower():
        return None

    relative = resolved.relative_to(base)
    rel_parts = list(relative.parts)
    if any("archive" in part.lower() for part in rel_parts[:-1]):
        return None

    stat = resolved.stat()
    compound = rel_parts[0] if len(rel_parts) > 0 else ""
    project = rel_parts[1] if len(rel_parts) > 1 else ""
    context = _extract_task_context(base, relative, compound, project)
    if context is None:
        return None

    task = context["task"]
    file_name = resolved.name
    program_key = resolved.stem.upper()
    rel_posix = relative.as_posix()

    return {
        "full_path": str(resolved),
        "rel_path": rel_posix,
        "compound": compound,
        "project": project,
        "task": task,
        "category": _infer_category(rel_posix),
        "file_name": file_name,
        "program_key": program_key,
        "extension": resolved.suffix.lower(),
        "role": _infer_role(rel_posix),
        "modified_time": stat.st_mtime,
        "size": stat.st_size,
        "content_hash": _file_sha256_hex(resolved),
    }


def _infer_category(rel_path: str) -> str:
    """Pick the segment after prog/qcprog and normalise to SDTM/ADAM/TFL/OTHER."""
    parts = [p.lower() for p in rel_path.split("/") if p]
    for idx, part in enumerate(parts[:-1]):
        if part in {"prog", "qcprog"}:
            nxt = parts[idx + 1]
            if nxt == "sdtm":
                return "SDTM"
            if nxt == "adam":
                return "ADAM"
            if nxt in {"tfl", "tfls"}:
                return "TFL"
    return "OTHER"


def _extract_task_context(
    base: Path,
    relative: Path,
    compound: str,
    project: str,
) -> dict[str, str] | None:
    rel_parts = list(relative.parts)
    if len(rel_parts) <= 2:
        return {"task": "(root)"}

    if rel_parts[2].upper() != "SP":
        return {"task": rel_parts[2]}

    if len(rel_parts) <= 4:
        return None

    candidate = rel_parts[3]
    if candidate.lower() == "documents":
        return None

    sp_root = base / compound / project / rel_parts[2]
    candidate_root = sp_root / candidate
    has_nested_task = (candidate_root / "task").is_dir()
    has_direct_roles = any((candidate_root / role).is_dir() for role in ROLE_ROOTS)
    if not has_nested_task and not has_direct_roles:
        return None

    remaining = rel_parts[4:-1]
    task_parts = ["SP", candidate]
    if has_nested_task:
        if remaining and remaining[0].lower() == "task":
            task_parts.append(remaining[0])
            remaining = remaining[1:]
        elif not has_direct_roles:
            return None

    if remaining and remaining[0].lower() == "documents":
        return None

    return {"task": "/".join(task_parts)}


def _collect_index_rows(scan_root: Path, base_path: Path | None = None) -> list[tuple]:
    """Scan *scan_root* using os.scandir + parallel hashing (full rebuild, no cache reuse)."""
    actual_base = (base_path or scan_root).resolve()
    target_files = _walk_target_files(scan_root, TARGET_EXTENSIONS)

    def _process(path: Path) -> tuple | None:
        try:
            entry = parse_index_entry(path, base_path=actual_base)
        except (FileNotFoundError, PermissionError, OSError):
            logger.warning("Skipping unreadable file during indexing: %s", path)
            return None
        if not entry:
            return None
        return _entry_to_tuple(entry)

    rows: list[tuple] = []
    with ThreadPoolExecutor(max_workers=_HASH_WORKERS) as pool:
        for result in pool.map(_process, target_files):
            if result is not None:
                rows.append(result)
    return rows


def _collect_index_rows_incremental(
    scan_root: Path,
    base_path: Path | None,
    existing: dict[str, tuple[float, int, str]],
) -> list[tuple]:
    """Incremental variant: reuse content_hash when mtime+size unchanged.

    *existing* maps ``full_path`` -> ``(modified_time, size, content_hash)``.
    """
    actual_base = (base_path or scan_root).resolve()
    files = _walk_target_files(scan_root, TARGET_EXTENSIONS)

    def _process(path: Path) -> tuple | None:
        try:
            resolved = path.resolve(strict=False)
            fp = str(resolved)
            prev = existing.get(fp)
            if prev is not None:
                stat = resolved.stat()
                if stat.st_mtime == prev[0] and stat.st_size == prev[1]:
                    entry = parse_index_entry(path, base_path=actual_base)
                    if entry is None:
                        return None
                    entry["content_hash"] = prev[2]
                    entry["modified_time"] = prev[0]
                    entry["size"] = prev[1]
                    return _entry_to_tuple(entry)
            entry = parse_index_entry(path, base_path=actual_base)
        except (FileNotFoundError, PermissionError, OSError):
            logger.warning("Skipping unreadable file during indexing: %s", path)
            return None
        if not entry:
            return None
        return _entry_to_tuple(entry)

    rows: list[tuple] = []
    with ThreadPoolExecutor(max_workers=_HASH_WORKERS) as pool:
        for result in pool.map(_process, files):
            if result is not None:
                rows.append(result)
    return rows


def _entry_to_tuple(entry: dict) -> tuple:
    return (
        entry["full_path"],
        entry["rel_path"],
        entry["compound"],
        entry["project"],
        entry["task"],
        entry.get("category", "OTHER"),
        entry["file_name"],
        entry["program_key"],
        entry["extension"],
        entry["role"],
        entry["modified_time"],
        entry["size"],
        entry["content_hash"],
    )


def _scan_available_scopes_sync() -> list[dict]:
    """Scan top 2 directory levels under PROJECTS_BASE_PATH (fast, no file I/O)."""
    base = PROJECTS_BASE_PATH.resolve()
    if not base.is_dir():
        return []
    scopes = []
    try:
        for compound_dir in sorted(base.iterdir()):
            if not compound_dir.is_dir():
                continue
            try:
                projects = sorted(p.name for p in compound_dir.iterdir() if p.is_dir())
            except PermissionError:
                projects = []
            scopes.append({"compound": compound_dir.name, "projects": projects})
    except PermissionError:
        pass
    return scopes


async def ensure_index() -> CodeIndexStatus:
    """Mark index as bootstrapped (lazy mode: no auto full-rebuild on startup)."""
    global _INDEX_BOOTSTRAPPED
    if _INDEX_BOOTSTRAPPED:
        return await get_status()
    async with _REBUILD_LOCK:
        if _INDEX_BOOTSTRAPPED:
            return await get_status()
        _INDEX_BOOTSTRAPPED = True
        return await get_status()


async def rebuild_index() -> dict[str, int | str]:
    """Rebuild the global file index from disk."""
    async with _REBUILD_LOCK:
        return await _rebuild_index_locked()


async def _rebuild_index_locked() -> dict[str, int | str]:
    global _INDEX_BOOTSTRAPPED
    _INDEX_BOOTSTRAPPED = False

    base = PROJECTS_BASE_PATH.resolve()
    if not base.is_dir():
        raise FileNotFoundError(f"Projects base path does not exist: {base}")

    db = await _get_index_db()
    existing = await _load_existing_index(db)
    rows = await asyncio.to_thread(
        _collect_index_rows_incremental, base, base, existing,
    )

    insert_sql = """
            INSERT INTO indexed_files (
                full_path, rel_path, compound, project, task, category,
                file_name, program_key, extension, role,
                modified_time, size, content_hash
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """

    await db.execute("BEGIN IMMEDIATE")
    try:
        await db.execute("DELETE FROM indexed_files")
        for start in range(0, len(rows), _INSERT_BATCH_SIZE):
            chunk = rows[start : start + _INSERT_BATCH_SIZE]
            await db.executemany(insert_sql, chunk)

        now = datetime.now().isoformat(timespec="seconds")
        await db.execute(
            """
            INSERT INTO code_index_runs (id, last_indexed_at, indexed_files)
            VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                last_indexed_at = excluded.last_indexed_at,
                indexed_files = excluded.indexed_files
            """,
            (now, len(rows)),
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    _INDEX_BOOTSTRAPPED = True
    logger.info("Rebuilt code index with %d files from %s", len(rows), base)
    return {"indexed_files": len(rows), "last_indexed_at": now}


async def get_status() -> CodeIndexStatus:
    """Return top-level code index status."""
    db = await _get_index_db()
    file_row = await _fetchone(
        db,
        """
        SELECT COUNT(*) AS indexed_files
        FROM indexed_files
        """,
    )
    group_row = await _fetchone(
        db,
        """
        SELECT COUNT(*) AS program_groups
        FROM (
            SELECT program_key, extension
            FROM indexed_files
            GROUP BY program_key, extension
        )
        """,
    )
    run_row = await _fetchone(
        db,
        """
        SELECT last_indexed_at
        FROM code_index_runs
        WHERE id = 1
        """,
    )
    last_indexed_at = None
    if run_row and run_row["last_indexed_at"]:
        last_indexed_at = datetime.fromisoformat(run_row["last_indexed_at"])
    return CodeIndexStatus(
        indexed_files=(file_row["indexed_files"] if file_row else 0),
        program_groups=(group_row["program_groups"] if group_row else 0),
        last_indexed_at=last_indexed_at,
    )


async def scan_available_scopes() -> list[dict]:
    """Return compound/project directories that exist on disk (fast scan, no file indexing)."""
    return await asyncio.to_thread(_scan_available_scopes_sync)


async def get_indexed_scopes() -> list[dict]:
    """Return compound/project pairs that have entries in the index."""
    await ensure_index()
    db = await _get_index_db()
    rows = await db.execute_fetchall(
        """
        SELECT compound, project, COUNT(*) AS file_count
        FROM indexed_files
        WHERE compound <> '' AND project <> ''
        GROUP BY compound, project
        ORDER BY compound ASC, project ASC
        """
    )
    return [
        {"compound": r["compound"], "project": r["project"], "file_count": r["file_count"]}
        for r in rows
    ]


async def index_scope(compound: str, project: str | None = None) -> dict:
    """Index only the files under a specific compound (and optionally project)."""
    global _INDEX_BOOTSTRAPPED
    base = PROJECTS_BASE_PATH.resolve()
    scan_root = base / compound
    if project:
        scan_root = scan_root / project
    if not scan_root.is_dir():
        raise FileNotFoundError(f"Scope path does not exist: {scan_root}")

    db = await _get_index_db()
    existing = await _load_existing_index(db, compound=compound, project=project)
    rows = await asyncio.to_thread(
        _collect_index_rows_incremental, scan_root, base, existing,
    )

    insert_sql = """
        INSERT INTO indexed_files (
            full_path, rel_path, compound, project, task, category,
            file_name, program_key, extension, role,
            modified_time, size, content_hash
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    await db.execute("BEGIN IMMEDIATE")
    try:
        if project:
            await db.execute(
                "DELETE FROM indexed_files WHERE compound = ? AND project = ?",
                (compound, project),
            )
        else:
            await db.execute(
                "DELETE FROM indexed_files WHERE compound = ?",
                (compound,),
            )
        for start in range(0, len(rows), _INSERT_BATCH_SIZE):
            chunk = rows[start : start + _INSERT_BATCH_SIZE]
            await db.executemany(insert_sql, chunk)
        now = datetime.now().isoformat(timespec="seconds")
        total_row = await _fetchone(db, "SELECT COUNT(*) AS n FROM indexed_files")
        total = total_row["n"] if total_row else len(rows)
        await db.execute(
            """
            INSERT INTO code_index_runs (id, last_indexed_at, indexed_files)
            VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                last_indexed_at = excluded.last_indexed_at,
                indexed_files = excluded.indexed_files
            """,
            (now, total),
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    _INDEX_BOOTSTRAPPED = True
    logger.info("Indexed scope %s/%s: %d files", compound, project or "*", len(rows))
    return {"compound": compound, "project": project, "indexed_files": len(rows), "last_indexed_at": now}


async def remove_scope(compound: str, project: str | None = None) -> dict:
    """Remove all indexed entries for a compound (and optionally a specific project)."""
    db = await _get_index_db()
    if project:
        await db.execute(
            "DELETE FROM indexed_files WHERE compound = ? AND project = ?",
            (compound, project),
        )
    else:
        await db.execute(
            "DELETE FROM indexed_files WHERE compound = ?",
            (compound,),
        )
    await db.commit()
    return {"removed": True, "compound": compound, "project": project}


async def get_contexts() -> CodeIndexContext:
    """Return distinct filter values for the code index UI."""
    await ensure_index()
    db = await _get_index_db()
    return CodeIndexContext(
        compounds=await _distinct_values(db, "compound"),
        projects=await _distinct_values(db, "project"),
        tasks=await _distinct_values(db, "task"),
        extensions=await _distinct_values(db, "extension"),
    )


async def get_filter_options(
    compound: str | None = None,
    project: str | None = None,
) -> CodeIndexFilterOptions:
    """Return distinct projects (and tasks) scoped by compound / project."""
    await ensure_index()
    if not compound:
        return CodeIndexFilterOptions()
    db = await _get_index_db()
    rows_p = await db.execute_fetchall(
        """
        SELECT DISTINCT project AS value
        FROM indexed_files
        WHERE compound = ? AND project <> ''
        ORDER BY project ASC
        """,
        (compound,),
    )
    projects = [r["value"] for r in rows_p if r["value"]]
    if project:
        rows_t = await db.execute_fetchall(
            """
            SELECT DISTINCT task AS value
            FROM indexed_files
            WHERE compound = ? AND project = ? AND task <> ''
            ORDER BY task ASC
            """,
            (compound, project),
        )
    else:
        rows_t = await db.execute_fetchall(
            """
            SELECT DISTINCT task AS value
            FROM indexed_files
            WHERE compound = ? AND task <> ''
            ORDER BY task ASC
            """,
            (compound,),
        )
    tasks = [r["value"] for r in rows_t if r["value"]]

    cat_clauses = ["category <> ''"]
    cat_params: list[object] = []
    if compound:
        cat_clauses.append("compound = ?")
        cat_params.append(compound)
    if project:
        cat_clauses.append("project = ?")
        cat_params.append(project)
    rows_c = await db.execute_fetchall(
        f"SELECT DISTINCT category AS value FROM indexed_files WHERE {' AND '.join(cat_clauses)} ORDER BY category ASC",
        tuple(cat_params),
    )
    categories = [r["value"] for r in rows_c if r["value"]]
    return CodeIndexFilterOptions(projects=projects, tasks=tasks, categories=categories)


async def query_program_groups(
    search: str = "",
    compound: str | None = None,
    project: str | None = None,
    task: str | None = None,
    category: str | None = None,
    extension: str | None = None,
    role: str | None = None,
    limit: int = 200,
) -> list[ProgramGroup]:
    """Return aggregated program groups from the index."""
    await ensure_index()
    db = await _get_index_db()
    regex = _compile_search_regex(search)
    where_sql, params = _build_filters(
        search="" if regex else search,
        compound=compound,
        project=project,
        task=task,
        category=category,
        extension=extension,
        role=role,
    )
    sql = f"""
        SELECT
            program_key,
            extension,
            program_key || extension AS display_name,
            COUNT(*) AS version_count,
            MAX(modified_time) AS latest_modified_time,
            GROUP_CONCAT(DISTINCT task) AS tasks,
            GROUP_CONCAT(DISTINCT project) AS projects,
            GROUP_CONCAT(DISTINCT compound) AS compounds
        FROM indexed_files
        {where_sql}
        GROUP BY program_key, extension
        ORDER BY latest_modified_time DESC, display_name ASC
        LIMIT ?
    """
    rows = await db.execute_fetchall(sql, (*params, limit))
    groups = [
        ProgramGroup(
            program_key=row["program_key"],
            extension=row["extension"],
            display_name=row["display_name"],
            version_count=row["version_count"],
            latest_modified_time=datetime.fromtimestamp(row["latest_modified_time"]),
            tasks=_split_csv(row["tasks"]),
            projects=_split_csv(row["projects"]),
            compounds=_split_csv(row["compounds"]),
        )
        for row in rows
    ]
    if regex is None:
        return groups
    return [
        group for group in groups
        if regex.search(group.display_name) or regex.search(group.program_key)
    ]


async def get_program_timeline(
    program_key: str,
    extension: str | None = None,
    compound: str | None = None,
    project: str | None = None,
    task: str | None = None,
    role: str | None = None,
) -> list[ProgramVersion]:
    """Return every indexed version for a program."""
    await ensure_index()
    db = await _get_index_db()
    extra_filters: list[str] = ["program_key = ?"]
    params: list[object] = [program_key.upper()]
    if extension:
        extra_filters.append("extension = ?")
        params.append(extension.lower())
    where_sql, filter_params = _build_filters(
        compound=compound,
        project=project,
        task=task,
        role=role,
    )
    if where_sql == "WHERE 1 = 1":
        query_where = "WHERE " + " AND ".join(extra_filters)
    else:
        query_where = where_sql + " AND " + " AND ".join(extra_filters)
    rows = await db.execute_fetchall(
        f"""
        SELECT
            id, full_path, rel_path, compound, project, task,
            file_name, program_key, extension, role,
            modified_time, size, content_hash
        FROM indexed_files
        {query_where}
        ORDER BY modified_time DESC, full_path ASC
        """,
        (*filter_params, *params),
    )
    return [_row_to_program_version(row) for row in rows]


async def get_indexed_file(file_id: int) -> IndexedFile:
    """Return one indexed file by id."""
    await ensure_index()
    db = await _get_index_db()
    row = await _fetchone(
        db,
        """
        SELECT
            id, full_path, rel_path, compound, project, task,
            file_name, program_key, extension, role,
            modified_time, size, content_hash
        FROM indexed_files
        WHERE id = ?
        """,
        (file_id,),
    )
    if not row:
        raise FileNotFoundError(f"Indexed file not found: {file_id}")
    return _row_to_indexed_file(row)


async def preview_indexed_file(file_id: int, max_bytes: int = 2_000_000) -> dict:
    """Read preview content for one indexed file."""
    item = await get_indexed_file(file_id)
    text, encoding, truncated, size_bytes = read_text(item.full_path, max_bytes=max_bytes)
    return {
        "file": item.model_dump(),
        "text": text,
        "encoding": encoding,
        "size_bytes": size_bytes,
        "truncated": truncated,
        "line_count": text.count("\n") + (1 if text else 0),
    }


async def read_indexed_file_text(file_id: int) -> tuple[str, str, IndexedFile]:
    """Read full text for one indexed file."""
    item = await get_indexed_file(file_id)
    text, _, _ = read_text_full(item.full_path)
    return text, item.display_name if hasattr(item, "display_name") else item.file_name, item


async def get_qc_timing_rows(
    compound: str | None = None,
    project: str | None = None,
    task: str | None = None,
    category: str | None = None,
) -> list[QcTimingRow]:
    """Compare main vs QC log mtimes using indexed data (SQL window aggregation)."""
    await ensure_index()
    db = await _get_index_db()
    where_sql, params = _build_filters(
        compound=compound, project=project, task=task, category=category
    )

    sql = f"""
        WITH base AS (
            SELECT
                id,
                full_path,
                rel_path,
                compound,
                project,
                task,
                category,
                file_name,
                program_key,
                extension,
                role,
                modified_time,
                size,
                content_hash,
                CASE
                    WHEN role = 'qc' AND UPPER(program_key) LIKE 'QC_%'
                        THEN SUBSTR(UPPER(program_key), 4)
                    ELSE UPPER(program_key)
                END AS pair_key
            FROM indexed_files
            {where_sql}
        ),
        main_log AS (
            SELECT * FROM (
                SELECT
                    id,
                    full_path,
                    project,
                    task,
                    category,
                    pair_key,
                    modified_time,
                    ROW_NUMBER() OVER (
                        PARTITION BY project, task, pair_key
                        ORDER BY modified_time DESC, id DESC
                    ) AS rn
                FROM base
                WHERE extension = '.log' AND role <> 'qc'
            ) WHERE rn = 1
        ),
        qc_log AS (
            SELECT * FROM (
                SELECT
                    id,
                    full_path,
                    project,
                    task,
                    pair_key,
                    modified_time,
                    ROW_NUMBER() OVER (
                        PARTITION BY project, task, pair_key
                        ORDER BY modified_time DESC, id DESC
                    ) AS rn
                FROM base
                WHERE extension = '.log' AND role = 'qc'
            ) WHERE rn = 1
        ),
        main_sas AS (
            SELECT * FROM (
                SELECT
                    id,
                    full_path,
                    project,
                    task,
                    pair_key,
                    ROW_NUMBER() OVER (
                        PARTITION BY project, task, pair_key
                        ORDER BY modified_time DESC, id DESC
                    ) AS rn
                FROM base
                WHERE extension = '.sas' AND role <> 'qc'
            ) WHERE rn = 1
        ),
        qc_sas AS (
            SELECT * FROM (
                SELECT
                    id,
                    full_path,
                    project,
                    task,
                    pair_key,
                    ROW_NUMBER() OVER (
                        PARTITION BY project, task, pair_key
                        ORDER BY modified_time DESC, id DESC
                    ) AS rn
                FROM base
                WHERE extension = '.sas' AND role = 'qc'
            ) WHERE rn = 1
        )
        SELECT
            ml.task AS task,
            ml.category AS category,
            ml.pair_key AS program,
            ml.modified_time AS main_log_mtime,
            ql.modified_time AS qc_log_mtime,
            CASE
                WHEN ql.id IS NULL THEN 1
                WHEN ql.modified_time < ml.modified_time THEN 1
                ELSE 0
            END AS stale,
            CASE
                WHEN ql.id IS NULL THEN 'qc-missing'
                WHEN ql.modified_time < ml.modified_time THEN 'qc-older'
                ELSE 'ok'
            END AS reason,
            ml.full_path AS main_log_path,
            ql.full_path AS qc_log_path,
            ms.full_path AS main_sas_path,
            qs.full_path AS qc_sas_path
        FROM main_log ml
        LEFT JOIN qc_log ql
            ON ql.project = ml.project
            AND ql.task = ml.task
            AND ql.pair_key = ml.pair_key
        LEFT JOIN main_sas ms
            ON ms.project = ml.project
            AND ms.task = ml.task
            AND ms.pair_key = ml.pair_key
        LEFT JOIN qc_sas qs
            ON qs.project = ml.project
            AND qs.task = ml.task
            AND qs.pair_key = ml.pair_key
        ORDER BY
            CASE
                WHEN ql.id IS NULL OR ql.modified_time < ml.modified_time THEN 0
                ELSE 1
            END ASC,
            ml.task COLLATE NOCASE ASC,
            ml.pair_key COLLATE NOCASE ASC
        """

    rows = await db.execute_fetchall(sql, params)
    out: list[QcTimingRow] = []
    for row in rows:
        qc_mtime = row["qc_log_mtime"]
        out.append(
            QcTimingRow(
                task=row["task"],
                category=row["category"] or "OTHER",
                program=row["program"],
                main_log_mtime=datetime.fromtimestamp(row["main_log_mtime"]),
                qc_log_mtime=datetime.fromtimestamp(qc_mtime) if qc_mtime is not None else None,
                stale=bool(row["stale"]),
                reason=row["reason"],
                main_log_path=row["main_log_path"],
                qc_log_path=row["qc_log_path"],
                main_sas_path=row["main_sas_path"],
                qc_sas_path=row["qc_sas_path"],
            )
        )
    return out


async def resolve_indexed_diff_target(file_id: int) -> tuple[str, str, str]:
    """Resolve an indexed file into full text + UI label + path."""
    item = await get_indexed_file(file_id)
    text, _, _ = read_text_full(item.full_path)
    label = f"{item.display_name if hasattr(item, 'display_name') else item.file_name} | {item.project}/{item.task}"
    return text, label, item.full_path


def _infer_role(rel_path: str) -> str:
    parts = [part.lower() for part in rel_path.split("/") if part]
    if any(("qcprog" in part) or (part == "qc") or part.startswith("qc_") for part in parts):
        return "qc"
    if parts:
        return "main"
    return "unknown"


def _build_filters(
    search: str = "",
    compound: str | None = None,
    project: str | None = None,
    task: str | None = None,
    category: str | None = None,
    extension: str | None = None,
    role: str | None = None,
) -> tuple[str, tuple[object, ...]]:
    clauses = ["1 = 1"]
    params: list[object] = []
    if compound:
        clauses.append("compound = ?")
        params.append(compound)
    if project:
        clauses.append("project = ?")
        params.append(project)
    if task:
        clauses.append("task = ?")
        params.append(task)
    if category and category != "ALL":
        clauses.append("category = ?")
        params.append(category.upper())
    if extension:
        clauses.append("extension = ?")
        params.append(extension.lower())
    if role and role != "all":
        clauses.append("role = ?")
        params.append(role)
    if search.strip():
        like = f"%{search.strip().upper()}%"
        clauses.append(
            """
            (
                UPPER(program_key) LIKE ?
                OR UPPER(file_name) LIKE ?
                OR UPPER(rel_path) LIKE ?
            )
            """
        )
        params.extend([like, like, like])
    return "WHERE " + " AND ".join(clauses), tuple(params)


def _compile_search_regex(search: str) -> re.Pattern[str] | None:
    query = (search or "").strip()
    if not query:
        return None
    pattern = ""
    flags = 0
    if query.startswith("re:"):
        pattern = query[3:]
        flags = re.IGNORECASE
    elif len(query) >= 2 and query.startswith("/") and "/" in query[1:]:
        last = query.rfind("/")
        if last > 0:
            pattern = query[1:last]
            raw_flags = query[last + 1 :]
            for ch in raw_flags:
                if ch == "i":
                    flags |= re.IGNORECASE
                elif ch == "m":
                    flags |= re.MULTILINE
                elif ch == "s":
                    flags |= re.DOTALL
    if not pattern:
        return None
    try:
        return re.compile(pattern, flags)
    except re.error as exc:
        raise ValueError(f"Invalid regex search: {exc}") from exc


async def _distinct_values(db, column: str) -> list[str]:
    rows = await db.execute_fetchall(
        f"""
        SELECT DISTINCT {column} AS value
        FROM indexed_files
        WHERE {column} <> ''
        ORDER BY {column} ASC
        """
    )
    return [row["value"] for row in rows if row["value"]]


async def _fetchone(db, sql: str, params: tuple[object, ...] = ()) -> object | None:
    rows = await db.execute_fetchall(sql, params)
    return rows[0] if rows else None


async def _load_existing_index(
    db,
    compound: str | None = None,
    project: str | None = None,
) -> dict[str, tuple[float, int, str]]:
    """Load existing indexed entries as {full_path: (mtime, size, hash)} for incremental comparison."""
    clauses = []
    params: list[object] = []
    if compound:
        clauses.append("compound = ?")
        params.append(compound)
    if project:
        clauses.append("project = ?")
        params.append(project)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = await db.execute_fetchall(
        f"SELECT full_path, modified_time, size, content_hash FROM indexed_files {where}",
        tuple(params),
    )
    return {r["full_path"]: (r["modified_time"], r["size"], r["content_hash"]) for r in rows}


async def _get_index_db():
    try:
        return await get_db()
    except RuntimeError:
        await init_db()
        return await get_db()


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return sorted({part for part in value.split(",") if part})


def _row_to_indexed_file(row) -> IndexedFile:
    return IndexedFile(
        id=row["id"],
        full_path=row["full_path"],
        rel_path=row["rel_path"],
        compound=row["compound"],
        project=row["project"],
        task=row["task"],
        file_name=row["file_name"],
        program_key=row["program_key"],
        extension=row["extension"],
        role=row["role"],
        modified_time=datetime.fromtimestamp(row["modified_time"]),
        size=row["size"],
        content_hash=row["content_hash"],
    )


def _row_to_program_version(row) -> ProgramVersion:
    return ProgramVersion(**_row_to_indexed_file(row).model_dump())
