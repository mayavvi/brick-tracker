"""API routes for user identity, profile, avatar, and preferences."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from auth import User, get_current_user
from config import AVATARS_DIR
from database import (
    get_preferences,
    get_user_profile,
    save_preferences,
    update_user_avatar,
    update_user_display_name,
    upsert_user,
)
from models import UserInfo, UserPreferences, UserProfileUpdate, WorkstationPrefs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/user", tags=["user"])

_ALLOWED_AVATAR_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_MAX_AVATAR_BYTES = 2 * 1024 * 1024  # 2 MB
_SAFE_USERNAME = re.compile(r"^[A-Za-z0-9_.-]+$")


def _avatar_url_for(username: str, avatar_path: str) -> str:
    if not avatar_path:
        return ""
    return f"/api/user/avatar/{username}"


@router.get("/me", response_model=UserInfo)
async def me(user: User = Depends(get_current_user)) -> UserInfo:
    """Return the identity of the current user and touch last_active."""
    await upsert_user(user.username, user.display_name)
    profile = await get_user_profile(user.username)
    return UserInfo(
        username=user.username,
        display_name=profile.get("display_name") or user.display_name,
        avatar_url=_avatar_url_for(user.username, profile.get("avatar_path", "")),
    )


@router.put("/profile", response_model=UserInfo)
async def update_profile(
    payload: UserProfileUpdate,
    user: User = Depends(get_current_user),
) -> UserInfo:
    """Update the user's display name."""
    name = payload.display_name.strip()
    await upsert_user(user.username, user.display_name)
    await update_user_display_name(user.username, name)
    profile = await get_user_profile(user.username)
    return UserInfo(
        username=user.username,
        display_name=profile.get("display_name") or user.display_name,
        avatar_url=_avatar_url_for(user.username, profile.get("avatar_path", "")),
    )


@router.post("/avatar", response_model=UserInfo)
async def upload_avatar(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
) -> UserInfo:
    """Upload and persist a new avatar for the current user."""
    if not _SAFE_USERNAME.match(user.username):
        raise HTTPException(status_code=400, detail="Unsupported username for avatar storage")

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED_AVATAR_EXTS:
        raise HTTPException(status_code=400, detail="Only PNG/JPG/WebP/GIF are accepted")

    AVATARS_DIR.mkdir(parents=True, exist_ok=True)

    # Remove any previous avatar with a different extension to avoid stale files.
    for ext in _ALLOWED_AVATAR_EXTS:
        old = AVATARS_DIR / f"{user.username}{ext}"
        if old.exists() and ext != suffix:
            try:
                old.unlink()
            except OSError:
                logger.warning("Failed to remove old avatar: %s", old)

    target = AVATARS_DIR / f"{user.username}{suffix}"
    written = 0
    with target.open("wb") as fh:
        while chunk := await file.read(64 * 1024):
            written += len(chunk)
            if written > _MAX_AVATAR_BYTES:
                fh.close()
                target.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Avatar must be smaller than 2 MB")
            fh.write(chunk)

    await upsert_user(user.username, user.display_name)
    await update_user_avatar(user.username, target.name)
    profile = await get_user_profile(user.username)
    return UserInfo(
        username=user.username,
        display_name=profile.get("display_name") or user.display_name,
        avatar_url=_avatar_url_for(user.username, profile.get("avatar_path", "")),
    )


@router.get("/avatar/{username}")
async def get_avatar(username: str) -> FileResponse:
    """Serve the avatar image for *username*."""
    if not _SAFE_USERNAME.match(username):
        raise HTTPException(status_code=400, detail="Invalid username")
    profile = await get_user_profile(username)
    avatar_name = profile.get("avatar_path") or ""
    if not avatar_name:
        raise HTTPException(status_code=404, detail="No avatar")
    target = AVATARS_DIR / avatar_name
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Avatar file missing")
    return FileResponse(target)


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
    """Merge tracker preferences without clobbering workstation prefs."""
    raw = await get_preferences(user.username)
    raw.update(prefs.model_dump(mode="json"))
    await save_preferences(user.username, raw)
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
