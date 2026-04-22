"""Main/QC log timing checks for file-compare module."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from models import FileEntry, QcTimingRow
from services.file_index import build_index


def check_study(study_id: str) -> list[QcTimingRow]:
    """Compare main vs QC log mtimes for one study.

    Pairing key: (task, program-basename).
    Baseline is main log. Missing/older QC log is marked stale.
    """
    indexed = build_index(study_id)
    if not indexed:
        return []

    main_logs: dict[tuple[str, str], FileEntry] = {}
    qc_logs: dict[tuple[str, str], FileEntry] = {}
    main_sas: dict[tuple[str, str], FileEntry] = {}
    qc_sas: dict[tuple[str, str], FileEntry] = {}

    for item in indexed:
        key = (item.task, _program_name(item.abs_path))
        if item.kind == "log":
            if item.role == "qc":
                _pick_latest(qc_logs, key, item)
            else:
                _pick_latest(main_logs, key, item)
        elif item.kind == "sas":
            if item.role == "qc":
                _pick_latest(qc_sas, key, item)
            else:
                _pick_latest(main_sas, key, item)

    rows: list[QcTimingRow] = []
    for key in sorted(main_logs.keys(), key=lambda x: (x[0].lower(), x[1].lower())):
        task, program = key
        main_item = main_logs.get(key)
        qc_item = qc_logs.get(key)
        if main_item is None:
            continue

        if qc_item is None:
            stale = True
            reason = "qc-missing"
        elif qc_item.mtime < main_item.mtime:
            stale = True
            reason = "qc-older"
        else:
            stale = False
            reason = "ok"

        rows.append(
            QcTimingRow(
                task=task,
                program=program,
                main_log_mtime=_to_dt(main_item),
                qc_log_mtime=_to_dt(qc_item),
                stale=stale,
                reason=reason,
                main_log_path=main_item.abs_path,
                qc_log_path=qc_item.abs_path if qc_item else None,
                main_sas_path=main_sas.get(key).abs_path if key in main_sas else None,
                qc_sas_path=qc_sas.get(key).abs_path if key in qc_sas else None,
            )
        )

    rows.sort(key=lambda r: (not r.stale, r.task.lower(), r.program.lower()))
    return rows


def _program_name(abs_path: str) -> str:
    return Path(abs_path).stem.lower()


def _to_dt(item: FileEntry | None) -> datetime | None:
    if not item:
        return None
    return datetime.fromtimestamp(item.mtime)


def _pick_latest(
    mapping: dict[tuple[str, str], FileEntry],
    key: tuple[str, str],
    item: FileEntry,
) -> None:
    current = mapping.get(key)
    if current is None or item.mtime >= current.mtime:
        mapping[key] = item

