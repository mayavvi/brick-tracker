"""Safe file reading helpers for file-compare module."""

from __future__ import annotations

import hashlib
from pathlib import Path

from config import PROJECTS_BASE_PATH

_ENCODING_CANDIDATES = ("utf-8-sig", "utf-8", "gbk", "cp936", "latin-1")
_PROJECTS_BASE_RESOLVED = PROJECTS_BASE_PATH.resolve()


def resolve_safe_path(abs_path: str) -> Path:
    """Resolve *abs_path* and ensure it stays inside PROJECTS_BASE_PATH."""
    p = Path(abs_path).expanduser().resolve(strict=False)
    if not p.is_relative_to(_PROJECTS_BASE_RESOLVED):
        raise PermissionError("路径不在允许范围内")
    return p


def to_rel_path(path: Path) -> str:
    """Return path relative to PROJECTS_BASE_PATH with POSIX separators."""
    resolved = path.resolve(strict=False)
    if not resolved.is_relative_to(_PROJECTS_BASE_RESOLVED):
        raise PermissionError("路径不在允许范围内")
    return resolved.relative_to(_PROJECTS_BASE_RESOLVED).as_posix()


def read_text(abs_path: str | Path, max_bytes: int = 2_000_000) -> tuple[str, str, bool, int]:
    """Read a file in read-only mode via Path.read_bytes and decode text.

    Returns ``(text, encoding, truncated, size_bytes)``.
    """
    path = resolve_safe_path(str(abs_path))
    path = path.resolve(strict=True)
    if not path.is_relative_to(_PROJECTS_BASE_RESOLVED):
        raise PermissionError("路径不在允许范围内")

    if not path.is_file():
        raise FileNotFoundError(str(path))

    raw = path.read_bytes()
    text, encoding, truncated = decode_bytes(raw, max_bytes=max_bytes)
    return text, encoding, truncated, len(raw)

def decode_bytes(data: bytes, max_bytes: int | None = None) -> tuple[str, str, bool]:
    """Decode *data* with best-effort encoding detection."""
    truncated = False
    view = data
    if max_bytes is not None and len(data) > max_bytes:
        truncated = True
        view = data[:max_bytes]

    for enc in _ENCODING_CANDIDATES:
        try:
            return view.decode(enc), enc, truncated
        except UnicodeDecodeError:
            continue

    # latin-1 should always decode, keep this as a final fallback guard.
    return view.decode("latin-1", errors="replace"), "latin-1", truncated


def read_text_full(abs_path: str | Path) -> tuple[str, str, int]:
    """Read and decode the whole file content."""
    path = resolve_safe_path(str(abs_path))
    path = path.resolve(strict=True)
    if not path.is_relative_to(_PROJECTS_BASE_RESOLVED):
        raise PermissionError("路径不在允许范围内")
    if not path.is_file():
        raise FileNotFoundError(str(path))
    raw = path.read_bytes()
    text, encoding, _ = decode_bytes(raw, max_bytes=None)
    return text, encoding, len(raw)


def sha256_bytes(data: bytes) -> str:
    """Return SHA-256 hex digest for bytes."""
    return hashlib.sha256(data).hexdigest()
