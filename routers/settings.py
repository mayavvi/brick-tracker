"""Read/write app-level settings (settings.json next to exe)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import config

router = APIRouter(prefix="/api/settings", tags=["settings"])


class AppSettings(BaseModel):
    projects_base_path: str
    projects_base_path_active: str
    projects_base_path_exists: bool
    needs_restart: bool


_pending_restart: bool = False


def _build_response(saved_value: str) -> AppSettings:
    return AppSettings(
        projects_base_path=saved_value,
        projects_base_path_active=str(config.PROJECTS_BASE_PATH),
        projects_base_path_exists=Path(saved_value).is_dir() if saved_value else False,
        needs_restart=_pending_restart,
    )


@router.get("", response_model=AppSettings)
def read_settings() -> AppSettings:
    saved = config._load_settings().get("projects_base_path") or str(config.PROJECTS_BASE_PATH)
    return _build_response(saved)


class UpdateSettings(BaseModel):
    projects_base_path: str


@router.put("", response_model=AppSettings)
def update_settings(body: UpdateSettings) -> AppSettings:
    global _pending_restart
    new_path = body.projects_base_path.strip()
    if not new_path:
        raise HTTPException(status_code=400, detail="路径不能为空")
    if not Path(new_path).is_dir():
        raise HTTPException(status_code=400, detail=f"路径不存在或不是目录：{new_path}")

    data = config._load_settings()
    data["projects_base_path"] = new_path
    config.save_settings(data)

    _pending_restart = new_path != str(config.PROJECTS_BASE_PATH)
    return _build_response(new_path)
