"""Global code index for preview, timeline, and compare workflows."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from config import DATABASE_PATH, PROJECTS_BASE_PATH
from database import get_db, init_db
from models import CodeIndexContext, CodeIndexStatus, IndexedFile, ProgramGroup, ProgramVersion, QcTimingRow
from services.file_reader import read_text, read_text_full

logger = logging.getLogger(__name__)

TARGET_EXTENSIONS = {".sas", ".log", ".lst"}
ROLE_ROOTS = {"prog", "qcprog", "data", "qcdata", "outputs"}


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
    raw = resolved.read_bytes()
    compound = rel_parts[0] if len(rel_parts) > 0 else ""
    project = rel_parts[1] if len(rel_parts) > 1 else ""
    context = _extract_task_context(base, relative, compound, project)
    if context is None:
        return None

    task = context["task"]
    file_name = resolved.name
    program_key = resolved.stem.upper()

    return {
        "full_path": str(resolved),
        "rel_path": relative.as_posix(),
        "compound": compound,
        "project": project,
        "task": task,
        "file_name": file_name,
        "program_key": program_key,
        "extension": resolved.suffix.lower(),
        "role": _infer_role(relative.as_posix()),
        "modified_time": stat.st_mtime,
        "size": stat.st_size,
        "content_hash": sha256(raw).hexdigest(),
    }


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


async def ensure_index() -> CodeIndexStatus:
    """Ensure the global index exists before serving queries."""
    db = await _get_index_db()
    row = await _fetchone(
        db,
        """
        SELECT COUNT(*) AS indexed_files
        FROM indexed_files
        """,
    )
    if row and row["indexed_files"] > 0:
        return await get_status()
    await rebuild_index()
    return await get_status()


async def rebuild_index() -> dict[str, int | str]:
    """Rebuild the global file index from disk."""
    base = PROJECTS_BASE_PATH.resolve()
    if not base.is_dir():
        raise FileNotFoundError(f"Projects base path does not exist: {base}")

    db = await _get_index_db()
    rows: list[tuple] = []

    for path in base.rglob("*"):
        if not path.is_file():
            continue
        try:
            entry = parse_index_entry(path, base_path=base)
        except (FileNotFoundError, PermissionError, OSError):
            logger.warning("Skipping unreadable file during indexing: %s", path)
            continue
        if not entry:
            continue
        rows.append(
            (
                entry["full_path"],
                entry["rel_path"],
                entry["compound"],
                entry["project"],
                entry["task"],
                entry["file_name"],
                entry["program_key"],
                entry["extension"],
                entry["role"],
                entry["modified_time"],
                entry["size"],
                entry["content_hash"],
            )
        )

    await db.execute("DELETE FROM indexed_files")
    if rows:
        await db.executemany(
            """
            INSERT INTO indexed_files (
                full_path, rel_path, compound, project, task,
                file_name, program_key, extension, role,
                modified_time, size, content_hash
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

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


async def query_program_groups(
    search: str = "",
    compound: str | None = None,
    project: str | None = None,
    task: str | None = None,
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
) -> list[QcTimingRow]:
    """Compare main vs QC log mtimes using indexed data."""
    await ensure_index()
    db = await _get_index_db()
    where_sql, params = _build_filters(compound=compound, project=project, task=task)
    rows = await db.execute_fetchall(
        f"""
        SELECT
            id, full_path, rel_path, compound, project, task,
            file_name, program_key, extension, role,
            modified_time, size, content_hash
        FROM indexed_files
        {where_sql}
        ORDER BY modified_time DESC
        """,
        params,
    )

    main_logs: dict[tuple[str, str, str], IndexedFile] = {}
    qc_logs: dict[tuple[str, str, str], IndexedFile] = {}
    main_sas: dict[tuple[str, str, str], IndexedFile] = {}
    qc_sas: dict[tuple[str, str, str], IndexedFile] = {}

    for row in rows:
        item = _row_to_indexed_file(row)
        key = (item.project, item.task, _pairing_program_key(item.program_key, item.role))
        if item.extension == ".log":
            if item.role == "qc":
                _pick_latest(qc_logs, key, item)
            else:
                _pick_latest(main_logs, key, item)
        elif item.extension == ".sas":
            if item.role == "qc":
                _pick_latest(qc_sas, key, item)
            else:
                _pick_latest(main_sas, key, item)

    out: list[QcTimingRow] = []
    for key in sorted(main_logs.keys()):
        project_name, task_name, program = key
        main_item = main_logs[key]
        qc_item = qc_logs.get(key)
        if qc_item is None:
            stale = True
            reason = "qc-missing"
        elif qc_item.modified_time < main_item.modified_time:
            stale = True
            reason = "qc-older"
        else:
            stale = False
            reason = "ok"

        out.append(
            QcTimingRow(
                task=task_name,
                program=program,
                main_log_mtime=main_item.modified_time,
                qc_log_mtime=qc_item.modified_time if qc_item else None,
                stale=stale,
                reason=reason,
                main_log_path=main_item.full_path,
                qc_log_path=qc_item.full_path if qc_item else None,
                main_sas_path=main_sas.get(key).full_path if key in main_sas else None,
                qc_sas_path=qc_sas.get(key).full_path if key in qc_sas else None,
            )
        )
    out.sort(key=lambda row: (not row.stale, row.task.lower(), row.program.lower()))
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


def _pairing_program_key(program_key: str, role: str) -> str:
    normalized = program_key.upper()
    if role == "qc" and normalized.startswith("QC_"):
        return normalized[3:]
    return normalized


def _pick_latest(mapping: dict, key: tuple[str, str, str], item: IndexedFile) -> None:
    current = mapping.get(key)
    if current is None or item.modified_time >= current.modified_time:
        mapping[key] = item
