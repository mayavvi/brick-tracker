"""SQLite-backed storage for user-defined custom tasks with owner isolation."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime

from database import get_db
from models import CustomTask, CustomTaskCreate

logger = logging.getLogger(__name__)


class CustomTaskStore:
    """Async CRUD store backed by SQLite with per-user isolation."""

    async def list_all(self, owner: str) -> list[CustomTask]:
        """Return all tasks belonging to *owner*."""
        db = await get_db()
        rows = await db.execute_fetchall(
            "SELECT * FROM custom_tasks WHERE owner = ? ORDER BY created_at DESC",
            (owner,),
        )
        return [self._row_to_model(r) for r in rows]

    async def create(self, owner: str, data: CustomTaskCreate) -> CustomTask:
        """Insert a new custom task owned by *owner*."""
        db = await get_db()
        task_id = uuid.uuid4().hex[:12]
        now = datetime.now().isoformat(timespec="seconds")
        await db.execute(
            """
            INSERT INTO custom_tasks
                (id, owner, study_id, task_name, description,
                 main_person, main_status, qc_person, qc_status,
                 ddl, tags, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                owner,
                data.study_id,
                data.task_name,
                data.description,
                data.main_person,
                data.main_status,
                data.qc_person,
                data.qc_status,
                data.ddl.isoformat() if data.ddl else None,
                json.dumps(data.tags, ensure_ascii=False),
                now,
            ),
        )
        await db.commit()
        return CustomTask(
            **data.model_dump(),
            id=task_id,
            owner=owner,
            created_at=now,
        )

    async def update(
        self, owner: str, task_id: str, data: CustomTaskCreate
    ) -> CustomTask | None:
        """Update a task only if it belongs to *owner*."""
        db = await get_db()
        row = await db.execute_fetchall(
            "SELECT created_at FROM custom_tasks WHERE id = ? AND owner = ?",
            (task_id, owner),
        )
        if not row:
            return None

        created_at = row[0][0]
        await db.execute(
            """
            UPDATE custom_tasks SET
                study_id    = ?,
                task_name   = ?,
                description = ?,
                main_person = ?,
                main_status = ?,
                qc_person   = ?,
                qc_status   = ?,
                ddl         = ?,
                tags        = ?
            WHERE id = ? AND owner = ?
            """,
            (
                data.study_id,
                data.task_name,
                data.description,
                data.main_person,
                data.main_status,
                data.qc_person,
                data.qc_status,
                data.ddl.isoformat() if data.ddl else None,
                json.dumps(data.tags, ensure_ascii=False),
                task_id,
                owner,
            ),
        )
        await db.commit()
        return CustomTask(
            **data.model_dump(),
            id=task_id,
            owner=owner,
            created_at=created_at,
        )

    async def delete(self, owner: str, task_id: str) -> bool:
        """Delete a task only if it belongs to *owner*."""
        db = await get_db()
        cursor = await db.execute(
            "DELETE FROM custom_tasks WHERE id = ? AND owner = ?",
            (task_id, owner),
        )
        await db.commit()
        return cursor.rowcount > 0

    @staticmethod
    def _row_to_model(row: tuple) -> CustomTask:
        """Convert a raw SQLite row to a CustomTask model."""
        return CustomTask(
            id=row[0],
            owner=row[1],
            study_id=row[2],
            task_name=row[3],
            description=row[4],
            main_person=row[5],
            main_status=row[6],
            qc_person=row[7],
            qc_status=row[8],
            ddl=row[9],
            tags=json.loads(row[10]) if row[10] else [],
            created_at=row[11],
        )


custom_task_store = CustomTaskStore()
