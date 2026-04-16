"""API routes for user identity and preferences."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import User, get_current_user
from app.database import get_preferences, save_preferences, upsert_user
from app.models import UserInfo, UserPreferences

router = APIRouter(prefix="/api/user", tags=["user"])


@router.get("/me", response_model=UserInfo)
async def me(user: User = Depends(get_current_user)) -> UserInfo:
    """Return the identity of the current user and touch last_active."""
    await upsert_user(user.username, user.display_name)
    return UserInfo(username=user.username, display_name=user.display_name)


@router.get("/preferences", response_model=UserPreferences)
async def read_preferences(
    user: User = Depends(get_current_user),
) -> UserPreferences:
    """Return the saved preferences for the current user."""
    raw = await get_preferences(user.username)
    return UserPreferences(**raw)


@router.put("/preferences", response_model=UserPreferences)
async def write_preferences(
    prefs: UserPreferences,
    user: User = Depends(get_current_user),
) -> UserPreferences:
    """Create or update the current user's preferences."""
    await save_preferences(user.username, prefs.model_dump(mode="json"))
    return prefs
