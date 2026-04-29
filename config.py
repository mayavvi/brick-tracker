"""Application configuration via environment variables and settings.json."""

from __future__ import annotations

import json
import os
import platform
import sys
from pathlib import Path


def _default_base_path() -> str:
    if platform.system() == "Windows":
        return r"E:\2026\mnt\Development\Projects02"
    return "/mnt/Development/Projects02"


def _writable_root() -> Path:
    """Folder used for writable runtime data (DB, settings, etc).

    When frozen by PyInstaller, sit next to the .exe so users can see/back up
    their data. Otherwise sit next to this source file.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


_APP_ROOT = _writable_root()

SETTINGS_FILE: Path = _APP_ROOT / "settings.json"


def _load_settings() -> dict:
    if SETTINGS_FILE.is_file():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_settings(data: dict) -> None:
    """Persist settings.json. Caller is responsible for value validation."""
    SETTINGS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


_settings = _load_settings()


def _resolve_projects_base() -> str:
    env = os.environ.get("PROJECTS_BASE_PATH")
    if env:
        return env
    fs = _settings.get("projects_base_path")
    if isinstance(fs, str) and fs.strip():
        return fs
    return _default_base_path()


PROJECTS_BASE_PATH: Path = Path(_resolve_projects_base())

TRACKER_KEYWORD: str = "追踪日志"

DATA_SHEETS: list[str] = ["SPEC", "spec", "数据集", "TFLs"]

CACHE_TTL_SECONDS: int = int(os.environ.get("CACHE_TTL_SECONDS", "300"))

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASE_PATH: Path = Path(
    os.environ.get(
        "DATABASE_PATH",
        str(_APP_ROOT / "data" / "tracker.db"),
    )
)

AVATARS_DIR: Path = DATABASE_PATH.parent / "avatars"
