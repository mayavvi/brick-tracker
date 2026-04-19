"""User identity resolution for Posit Connect and local development."""

from __future__ import annotations

import base64
import json
import logging
import os

from fastapi import HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Posit Connect may use different header names across versions.
# Try each in order and use the first non-empty value found.
_GUID_HEADERS = [
    "posit-connect-user-id",
    "rstudio-connect-user-id",
    "x-rstudio-connect-user-id",
    "x-posit-connect-user-id",
]
_NAME_HEADERS = [
    "posit-connect-user",
    "x-rstudio-connect-user",
    "rstudio-connect-user",
]


class User(BaseModel):
    """Authenticated user identity."""

    username: str
    display_name: str = ""


def is_posit_connect() -> bool:
    """Return True when the app is running inside Posit Connect."""
    return os.environ.get("RSTUDIO_PRODUCT") == "CONNECT"


def get_current_user(request: Request) -> User:
    """FastAPI dependency that resolves the current user.

    Resolution order on Posit Connect:
    1. Direct identity headers (Posit-Connect-User-Id and variants)
    2. JWT in RStudio-Connect-Credentials (API/OAuth integrations)
    3. Process-level USER env var as last resort

    In local dev the user defaults to DEV_USERNAME or "dev-user".
    Query param ``_dev_user`` overrides for multi-user testing (dev only).
    """
    # Attach to request.state to avoid re-resolving within the same request
    if hasattr(request.state, "user"):
        return request.state.user  # type: ignore[return-value]

    if is_posit_connect():
        user = _resolve_posit_connect(request)
    else:
        dev_user = request.query_params.get(
            "_dev_user",
            os.environ.get("DEV_USERNAME", "dev-user"),
        )
        user = User(username=dev_user, display_name=dev_user)

    request.state.user = user
    return user


def _resolve_posit_connect(request: Request) -> User:
    """Resolve user identity from Posit Connect request context."""
    # 1. Direct identity headers (most reliable, sent on every browser request)
    guid = _first_header(request, _GUID_HEADERS)
    name = _first_header(request, _NAME_HEADERS)
    if guid or name:
        logger.debug("User resolved from Connect headers: guid=%s name=%s", guid, name)
        return User(username=guid or name, display_name=name or guid or "")

    # 2. JWT credential header (only present for OAuth/API integrations)
    cred = request.headers.get("rstudio-connect-credentials", "")
    if cred:
        try:
            parts = cred.split(".")
            padded = parts[1] + "=" * (-len(parts[1]) % 4)
            payload: dict = json.loads(base64.urlsafe_b64decode(padded))
            username = payload.get("user_guid", payload.get("sub", ""))
            display = payload.get("username", "")
            if username:
                logger.debug("User resolved from Connect JWT: %s", username)
                return User(username=username, display_name=display)
        except Exception:
            logger.exception("Failed to decode Connect credentials JWT")

    # 3. Process-level env var (last resort, may be the OS account running Connect)
    env_user = os.environ.get("USER") or os.environ.get("LOGNAME") or ""
    if env_user and env_user not in {"rstudio-connect", "root", "connect"}:
        logger.warning("Falling back to OS USER env var: %s", env_user)
        return User(username=env_user, display_name=env_user)

    # All paths exhausted — log which headers were actually present to help diagnose
    present = [k for k in request.headers.keys()
               if any(x in k.lower() for x in ("connect", "posit", "user", "rstudio"))]
    logger.error(
        "Cannot resolve Posit Connect user identity. "
        "Possibly-relevant headers present: %s. "
        "Set ENABLE_AUTH_DEBUG=1 and visit /api/debug/auth for full diagnostics.",
        present,
    )

    allow_anonymous = os.environ.get("ALLOW_ANONYMOUS", "0") == "1"
    if not allow_anonymous:
        raise HTTPException(
            status_code=401,
            detail="用户身份无法识别，请联系管理员（设置 ALLOW_ANONYMOUS=1 可临时绕过）",
        )
    return User(username="anonymous", display_name="Anonymous")


def _first_header(request: Request, candidates: list[str]) -> str:
    """Return the first non-empty header value from the candidate list."""
    for name in candidates:
        val = request.headers.get(name, "").strip()
        if val:
            return val
    return ""
