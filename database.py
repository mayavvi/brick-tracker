"""SQLite database initialization and connection management."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite

from config import DATABASE_PATH

logger = logging.getLogger(__name__)

_db: aiosqlite.Connection | None = None

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    username     TEXT PRIMARY KEY,
    display_name TEXT NOT NULL DEFAULT '',
    first_seen   TEXT NOT NULL,
    last_active  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_preferences (
    username    TEXT PRIMARY KEY,
    preferences TEXT NOT NULL DEFAULT '{}',
    updated_at  TEXT NOT NULL,
    FOREIGN KEY (username) REFERENCES users(username)
);

CREATE TABLE IF NOT EXISTS custom_tasks (
    id           TEXT PRIMARY KEY,
    owner        TEXT NOT NULL,
    study_id     TEXT NOT NULL,
    task_name    TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    main_person  TEXT NOT NULL DEFAULT '',
    main_status  TEXT NOT NULL DEFAULT '',
    qc_person    TEXT NOT NULL DEFAULT '',
    qc_status    TEXT NOT NULL DEFAULT '',
    ddl          TEXT,
    tags         TEXT NOT NULL DEFAULT '[]',
    created_at   TEXT NOT NULL,
    FOREIGN KEY (owner) REFERENCES users(username)
);

CREATE INDEX IF NOT EXISTS idx_custom_tasks_owner ON custom_tasks(owner);
"""


async def get_db() -> aiosqlite.Connection:
    """Return the singleton database connection, creating it on first call."""
    global _db
    if _db is None:
        raise RuntimeError("Database not initialised – call init_db() first")
    return _db


async def init_db() -> None:
    """Open the database and create tables if they don't exist."""
    global _db
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _db = await aiosqlite.connect(str(DATABASE_PATH))
    _db.row_factory = aiosqlite.Row
    await _db.executescript(_SCHEMA_SQL)
    await _db.commit()
    logger.info("Database initialised at %s", DATABASE_PATH)


async def close_db() -> None:
    """Close the database connection."""
    global _db
    if _db is not None:
        await _db.close()
        _db = None
        logger.info("Database connection closed")


# ---------------------------------------------------------------------------
# User helpers
# ---------------------------------------------------------------------------

async def upsert_user(username: str, display_name: str = "") -> None:
    """Insert a new user or update last_active timestamp."""
    db = await get_db()
    now = datetime.now().isoformat(timespec="seconds")
    await db.execute(
        """
        INSERT INTO users (username, display_name, first_seen, last_active)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(username) DO UPDATE SET
            display_name = COALESCE(NULLIF(excluded.display_name, ''), users.display_name),
            last_active  = excluded.last_active
        """,
        (username, display_name, now, now),
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Preferences helpers
# ---------------------------------------------------------------------------

async def get_preferences(username: str) -> dict[str, Any]:
    """Return the stored preferences dict for *username*, or empty dict."""
    db = await get_db()
    row = await db.execute_fetchall(
        "SELECT preferences FROM user_preferences WHERE username = ?",
        (username,),
    )
    if row:
        return json.loads(row[0][0])
    return {}


async def save_preferences(username: str, prefs: dict[str, Any]) -> None:
    """Upsert user preferences as a JSON blob."""
    db = await get_db()
    now = datetime.now().isoformat(timespec="seconds")
    await db.execute(
        """
        INSERT INTO user_preferences (username, preferences, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(username) DO UPDATE SET
            preferences = excluded.preferences,
            updated_at  = excluded.updated_at
        """,
        (username, json.dumps(prefs, ensure_ascii=False), now),
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Migration: legacy custom_tasks.json -> SQLite
# ---------------------------------------------------------------------------

async def migrate_legacy_tasks(json_path: Path, default_owner: str = "legacy") -> int:
    """Import tasks from the old JSON file into SQLite.

    Returns the number of tasks migrated.  The JSON file is renamed to
    ``*.bak`` after a successful migration.
    """
    if not json_path.exists():
        return 0

    try:
        tasks: list[dict] = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Failed to read legacy tasks from %s", json_path)
        return 0

    if not tasks:
        return 0

    db = await get_db()
    now = datetime.now().isoformat(timespec="seconds")

    await upsert_user(default_owner, "Legacy Import")

    count = 0
    for t in tasks:
        task_id = t.get("id", "")
        if not task_id:
            continue
        await db.execute(
            """
            INSERT OR IGNORE INTO custom_tasks
                (id, owner, study_id, task_name, description,
                 main_person, main_status, qc_person, qc_status,
                 ddl, tags, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                default_owner,
                t.get("study_id", ""),
                t.get("task_name", ""),
                t.get("description", ""),
                t.get("main_person", ""),
                t.get("main_status", ""),
                t.get("qc_person", ""),
                t.get("qc_status", ""),
                t.get("ddl"),
                json.dumps(t.get("tags", []), ensure_ascii=False),
                t.get("created_at", now),
            ),
        )
        count += 1

    await db.commit()

    backup = json_path.with_suffix(".json.bak")
    json_path.rename(backup)
    logger.info("Migrated %d legacy tasks -> SQLite, backup at %s", count, backup)
    return count
