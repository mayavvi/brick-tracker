"""Application configuration via environment variables."""

from __future__ import annotations

import os
import platform
from pathlib import Path


def _default_base_path() -> str:
    if platform.system() == "Windows":
        return r"E:\2026\mnt\Development\Projects02"
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

# Set to "1" to allow requests that can't be identified to proceed as "anonymous".
# Keep "0" (default) in production so identity failures surface as 401.
ALLOW_ANONYMOUS: bool = os.environ.get("ALLOW_ANONYMOUS", "0") == "1"

# Set to "1" to expose /api/debug/auth for diagnosing Connect header issues.
# Disable after confirming auth works correctly in production.
ENABLE_AUTH_DEBUG: bool = os.environ.get("ENABLE_AUTH_DEBUG", "0") == "1"

# Allowlist of Posit usernames that may use the app.
# Reads from env var ALLOWED_USERS first (comma-separated entries),
# then falls back to allowed_users.txt.
# Each entry: username:$sha256$salt_hex$digest_hex (see password_utils.hash_password).
# Empty = no restriction (everyone allowed).
_ALLOWED_USERS_FILE = Path(__file__).resolve().parent / "allowed_users.txt"


def get_allowed_users() -> dict[str, str]:
    """Return mapping username (lower) -> password hash string."""
    raw = os.environ.get("ALLOWED_USERS", "")
    if raw.strip():
        out: dict[str, str] = {}
        for segment in raw.split(","):
            segment = segment.strip()
            if not segment or ":" not in segment:
                continue
            name, h = segment.split(":", 1)
            name = name.strip().lower()
            if name:
                out[name] = h.strip()
        return out
    if _ALLOWED_USERS_FILE.is_file():
        try:
            text = _ALLOWED_USERS_FILE.read_text(encoding="utf-8")
            out: dict[str, str] = {}
            for line in text.splitlines():
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                if ":" not in s:
                    continue
                name, h = s.split(":", 1)
                name = name.strip().lower()
                if name:
                    out[name] = h.strip()
            return out
        except Exception:
            return {}
    return {}
