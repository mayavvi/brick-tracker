"""Diagnostics endpoints for troubleshooting deployment issues."""

from __future__ import annotations

import os

from fastapi import APIRouter, Request

from auth import COOKIE_NAME
from config import get_allowed_users

router = APIRouter(prefix="/api/debug", tags=["debug"])

_CHECK_VARS = [
    "ALLOWED_USERS",
    "PROJECTS_BASE_PATH",
    "DATABASE_PATH",
    "RSTUDIO_PRODUCT",
    "ENABLE_AUTH_DEBUG",
    "DEV_USERNAME",
]


@router.get("/env")
async def debug_env() -> dict:
    """Dump relevant environment variables — no auth required."""
    env = {}
    for k in _CHECK_VARS:
        val = os.environ.get(k)
        env[k] = val if val is not None else "<NOT SET>"
    env["_total_env_var_count"] = len(os.environ)
    return {"env": env, "parsed_allowed_users": sorted(get_allowed_users().keys()) or "(empty)"}


@router.get("/auth")
async def debug_auth(request: Request) -> dict:
    """Return auth-resolution diagnostics."""
    try:
        from auth import User, get_current_user
        resolved: User = get_current_user(request)
        resolved_dict = resolved.model_dump()
    except Exception as exc:
        resolved_dict = {"error": str(exc)}

    return {
        "resolved_user": resolved_dict,
        "cookie_present": bool(request.cookies.get(COOKIE_NAME, "")),
        "cookie_value": request.cookies.get(COOKIE_NAME, "<missing>"),
        "allowed_users": sorted(get_allowed_users().keys()) or "(no restriction)",
        "raw_env_ALLOWED_USERS": os.environ.get("ALLOWED_USERS", "<NOT SET>"),
    }
