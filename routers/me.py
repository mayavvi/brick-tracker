"""Personal workspace page — GET /me."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from auth import User, get_current_user
from database import get_db, upsert_user

router = APIRouter(tags=["me"])
_BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))


@router.get("/me", response_class=HTMLResponse)
async def workspace(request: Request, user: User = Depends(get_current_user)) -> HTMLResponse:
    """Render the personal workspace page."""
    await upsert_user(user.username, user.display_name)

    db = await get_db()
    row = await db.execute_fetchall(
        "SELECT first_seen, last_active FROM users WHERE username = ?",
        (user.username,),
    )
    user_row = dict(row[0]) if row else {"first_seen": "-", "last_active": "-"}

    task_count_rows = await db.execute_fetchall(
        "SELECT COUNT(*) as cnt FROM custom_tasks WHERE owner = ?",
        (user.username,),
    )
    task_count = task_count_rows[0]["cnt"] if task_count_rows else 0

    return templates.TemplateResponse(
        request,
        "me.html",
        {
            "user": user,
            "first_seen": user_row.get("first_seen", "-"),
            "last_active": user_row.get("last_active", "-"),
            "task_count": task_count,
            "shell_header": False,
        },
    )
