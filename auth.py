"""Local desktop stub — no real auth, single hardcoded user."""

from __future__ import annotations

from fastapi import Request
from pydantic import BaseModel


class User(BaseModel):
    username: str
    display_name: str = ""


_LOCAL_USER = User(username="local", display_name="本机用户")


def get_current_user(request: Request) -> User:
    return _LOCAL_USER
