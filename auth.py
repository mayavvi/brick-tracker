"""Cookie-based user identity with an environment-variable allowlist."""

from __future__ import annotations

import logging

from fastapi import HTTPException, Request
from pydantic import BaseModel

from config import DEV_USERNAME, get_allowed_users

logger = logging.getLogger(__name__)

COOKIE_NAME = "brick_user_v2"


class User(BaseModel):
    """Authenticated user identity."""

    username: str
    display_name: str = ""


def get_current_user(request: Request) -> User:
    """Resolve the current user from the session cookie.

    In local dev (no ALLOWED_USERS configured) falls back to DEV_USERNAME.
    """
    if hasattr(request.state, "user"):
        return request.state.user  # type: ignore[return-value]

    username = request.cookies.get(COOKIE_NAME, "").strip().lower()

    allowed = get_allowed_users()

    if not username:
        if not allowed:
            username = DEV_USERNAME
        else:
            raise HTTPException(status_code=401, detail="未登录")

    if allowed and username not in allowed:
        raise HTTPException(status_code=403, detail="用户不在允许列表中")

    user = User(username=username, display_name=username)
    request.state.user = user
    return user
