"""Auth diagnostics endpoint — only mounted when ENABLE_AUTH_DEBUG=1."""

from __future__ import annotations

import os

from fastapi import APIRouter, Request

from auth import COOKIE_NAME, User, get_current_user
from config import get_allowed_users

router = APIRouter(prefix="/api/debug", tags=["debug"])


@router.get("/auth")
async def debug_auth(request: Request) -> dict:
    """Return auth-resolution diagnostics."""
    try:
        resolved: User = get_current_user(request)
        resolved_dict = resolved.model_dump()
    except Exception as exc:
        resolved_dict = {"error": str(exc)}

    return {
        "resolved_user": resolved_dict,
        "cookie_present": bool(request.cookies.get(COOKIE_NAME, "")),
        "cookie_value": request.cookies.get(COOKIE_NAME, "<missing>"),
        "allowed_users": sorted(get_allowed_users()) or "(no restriction)",
        "relevant_env": {
            k: os.environ.get(k, "<not set>")
            for k in [
                "RSTUDIO_PRODUCT", "ALLOWED_USERS",
                "ENABLE_AUTH_DEBUG", "DEV_USERNAME",
            ]
        },
        "note": "Disable ENABLE_AUTH_DEBUG once auth is confirmed working.",
    }
