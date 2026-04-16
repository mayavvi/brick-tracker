"""Application configuration via environment variables."""

from __future__ import annotations

import os
import platform
from pathlib import Path


def _default_base_path() -> str:
    if platform.system() == "Windows":
        return r"E:\Dev_2026\mnt\Development\Projects02"
    return "/mnt/Development/Projects02"


PROJECTS_BASE_PATH: Path = Path(
    os.environ.get("PROJECTS_BASE_PATH", _default_base_path())
)

TRACKER_KEYWORD: str = "追踪日志"

DATA_SHEETS: list[str] = ["SPEC", "spec", "数据集", "TFLs"]

CACHE_TTL_SECONDS: int = int(os.environ.get("CACHE_TTL_SECONDS", "300"))

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
_APP_ROOT = Path(__file__).resolve().parent

DATABASE_PATH: Path = Path(
    os.environ.get(
        "DATABASE_PATH",
        str(_APP_ROOT / "data" / "tracker.db"),
    )
)

# ---------------------------------------------------------------------------
# User / Auth
# ---------------------------------------------------------------------------
DEV_USERNAME: str = os.environ.get("DEV_USERNAME", "dev-user")

IS_POSIT_CONNECT: bool = os.environ.get("RSTUDIO_PRODUCT") == "CONNECT"
