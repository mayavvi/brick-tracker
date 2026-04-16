"""API routes for custom (non-tracker) tasks with per-user isolation."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.auth import User, get_current_user
from app.models import CustomTask, CustomTaskCreate
from app.services.custom_tasks import custom_task_store

router = APIRouter(prefix="/api/custom-tasks", tags=["custom-tasks"])


@router.get("", response_model=list[CustomTask])
async def list_custom_tasks(
    user: User = Depends(get_current_user),
) -> list[CustomTask]:
    """Return all custom tasks belonging to the current user."""
    return await custom_task_store.list_all(user.username)


@router.post("", response_model=CustomTask, status_code=201)
async def create_custom_task(
    data: CustomTaskCreate,
    user: User = Depends(get_current_user),
) -> CustomTask:
    """Create a new custom task owned by the current user."""
    return await custom_task_store.create(user.username, data)


@router.put("/{task_id}", response_model=CustomTask)
async def update_custom_task(
    task_id: str,
    data: CustomTaskCreate,
    user: User = Depends(get_current_user),
) -> CustomTask:
    """Update an existing custom task (must belong to the current user)."""
    result = await custom_task_store.update(user.username, task_id, data)
    if result is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return result


@router.delete("/{task_id}", status_code=204)
async def delete_custom_task(
    task_id: str,
    user: User = Depends(get_current_user),
) -> None:
    """Delete a custom task (must belong to the current user)."""
    if not await custom_task_store.delete(user.username, task_id):
        raise HTTPException(status_code=404, detail="Task not found")
