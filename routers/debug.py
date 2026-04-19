"""Auth diagnostics endpoint — only mounted when ENABLE_AUTH_DEBUG=1."""

from __future__ import annotations

import os

from fastapi import APIRouter, Request

from auth import User, _GUID_HEADERS, _NAME_HEADERS, get_current_user

router = APIRouter(prefix="/api/debug", tags=["debug"])

_SENSITIVE_SUFFIXES = ("credentials", "token", "secret", "key", "password")


@router.get("/auth")
async def debug_auth(request: Request) -> dict:
    """Return auth-resolution diagnostics to help troubleshoot Posit Connect."""
    resolved: User = get_current_user(request)

    candidate_headers: dict[str, str] = {}
    for h in _GUID_HEADERS + _NAME_HEADERS + ["rstudio-connect-credentials"]:
        val = request.headers.get(h, "")
        if val:
            # Don't echo JWT/credential content, just signal presence
            candidate_headers[h] = "<present>" if any(s in h for s in _SENSITIVE_SUFFIXES) else val
        else:
            candidate_headers[h] = "<missing>"

    all_connect_headers = {
        k: ("<present>" if any(s in k.lower() for s in _SENSITIVE_SUFFIXES) else v)
        for k, v in request.headers.items()
        if any(x in k.lower() for x in ("connect", "posit", "rstudio", "user", "auth"))
    }

    relevant_env = {
        k: os.environ.get(k, "<not set>")
        for k in [
            "RSTUDIO_PRODUCT", "POSIT_PRODUCT",
            "USER", "LOGNAME",
            "ALLOW_ANONYMOUS", "ENABLE_AUTH_DEBUG",
            "DEV_USERNAME",
        ]
    }

    return {
        "resolved_user": resolved.model_dump(),
        "auth_mode": "posit-connect" if os.environ.get("RSTUDIO_PRODUCT") == "CONNECT" else "dev",
        "candidate_headers": candidate_headers,
        "all_connect_related_headers": all_connect_headers,
        "relevant_env": relevant_env,
        "note": "Disable ENABLE_AUTH_DEBUG once auth is confirmed working.",
    }
