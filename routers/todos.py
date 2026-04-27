"""API route for the unified personal todo list."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from auth import User, get_current_user
from models import TodoItem
from services.todo_aggregator import build_my_todos

router = APIRouter(prefix="/api/tasks", tags=["todos"])


@router.get("/my-todos", response_model=list[TodoItem])
async def my_todos(user: User = Depends(get_current_user)) -> list[TodoItem]:
    """Return merged open todos (tracker + custom) for the current user."""
    return await build_my_todos(user.username, user.display_name)
