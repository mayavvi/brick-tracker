"""API routes for user identity and preferences."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from auth import User, get_current_user
from database import get_preferences, save_preferences, upsert_user
from models import UserInfo, UserPreferences, WorkstationPrefs

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


@router.get("/workstation", response_model=WorkstationPrefs)
async def read_workstation_prefs(
    user: User = Depends(get_current_user),
) -> WorkstationPrefs:
    """Return the workstation-specific prefs (aliases + watched studies)."""
    raw = await get_preferences(user.username)
    return WorkstationPrefs(
        tracker_aliases=raw.get("tracker_aliases", []),
        watched_studies=raw.get("watched_studies", []),
    )


@router.put("/workstation", response_model=WorkstationPrefs)
async def write_workstation_prefs(
    wp: WorkstationPrefs,
    user: User = Depends(get_current_user),
) -> WorkstationPrefs:
    """Merge workstation prefs into the user's preferences blob."""
    raw = await get_preferences(user.username)
    raw["tracker_aliases"] = wp.tracker_aliases
    raw["watched_studies"] = wp.watched_studies
    await save_preferences(user.username, raw)
    return wp
