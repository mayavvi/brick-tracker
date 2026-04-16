"""User identity resolution for Posit Connect and local development."""

from __future__ import annotations

import base64
import json
import logging
import os

from fastapi import Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class User(BaseModel):
    """Authenticated user identity."""

    username: str
    display_name: str = ""


def is_posit_connect() -> bool:
    """Return True when the app is running inside Posit Connect."""
    return os.environ.get("RSTUDIO_PRODUCT") == "CONNECT"


def get_current_user(request: Request) -> User:
    """FastAPI dependency that resolves the current user.

    On Posit Connect the ``RStudio-Connect-Credentials`` header carries a
    JWT whose payload contains ``user_guid`` and ``username``.

    In local development the user defaults to ``DEV_USERNAME`` env-var or
    ``"dev-user"``.  A query parameter ``_dev_user`` can override it for
    quick multi-user testing.
    """
    if is_posit_connect():
        return _resolve_from_connect_header(request)

    dev_user = request.query_params.get(
        "_dev_user",
        os.environ.get("DEV_USERNAME", "dev-user"),
    )
    return User(username=dev_user, display_name=dev_user)


def _resolve_from_connect_header(request: Request) -> User:
    """Decode the Posit Connect JWT credential header."""
    cred = request.headers.get("rstudio-connect-credentials", "")
    if not cred:
        logger.warning("Missing RStudio-Connect-Credentials header")
        return User(username="anonymous", display_name="Anonymous")

    try:
        parts = cred.split(".")
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        payload: dict = json.loads(base64.urlsafe_b64decode(padded))
        return User(
            username=payload.get("user_guid", payload.get("sub", "unknown")),
            display_name=payload.get("username", ""),
        )
    except Exception:
        logger.exception("Failed to decode Connect credentials")
        return User(username="anonymous", display_name="Anonymous")
