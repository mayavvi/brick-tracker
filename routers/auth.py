"""Login / logout endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Response
from pydantic import BaseModel

from auth import COOKIE_NAME
from config import get_allowed_users

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str


class LoginResponse(BaseModel):
    ok: bool
    username: str = ""
    message: str = ""


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, response: Response) -> LoginResponse:
    username = body.username.strip().lower()
    if not username:
        return LoginResponse(ok=False, message="用户名不能为空")

    allowed = get_allowed_users()
    if allowed and username not in allowed:
        return LoginResponse(ok=False, message="你不在允许访问的用户列表中，请联系管理员")

    response.set_cookie(
        key=COOKIE_NAME,
        value=username,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 90,  # 90 days
        path="/",
    )
    return LoginResponse(ok=True, username=username)


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return {"ok": True}
