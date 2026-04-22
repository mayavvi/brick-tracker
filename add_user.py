#!/usr/bin/env python3
"""Add or update a user in allowed_users.txt with a password hash.

Usage:
  python add_user.py <username> <password>

Run from the project root after users send you their chosen password.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from password_utils import hash_password

_ROOT = Path(__file__).resolve().parent
_ALLOWED_FILE = _ROOT / "allowed_users.txt"


def _read_entries(path: Path) -> tuple[list[str], dict[str, str], list[str]]:
    """Header lines (comments + blanks), user->hash, key order as first seen."""
    if not path.is_file():
        return (
            [
                "# Allowed users: username:$sha256$salt$digest (one per line).\n",
                "# Lines starting with # are comments.\n",
                "# Set passwords with: python add_user.py <username> <password>\n",
            ],
            {},
            [],
        )
    header: list[str] = []
    users: dict[str, str] = {}
    order: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines(keepends=True):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            header.append(line if line.endswith("\n") else line + "\n")
            continue
        if ":" not in stripped:
            key = stripped.lower()
            if key and key not in users:
                users[key] = ""
                order.append(key)
            continue
        name, h = stripped.split(":", 1)
        key = name.strip().lower()
        if not key:
            continue
        users[key] = h.strip()
        if key not in order:
            order.append(key)
    return header, users, order


def _write_file(path: Path, header: list[str], users: dict[str, str], order: list[str]) -> None:
    body_lines = [f"{k}:{users[k]}\n" for k in order]
    text = "".join(header) + "".join(body_lines)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser(description="Register or update user password in allowed_users.txt")
    p.add_argument("username", help="Posit-style username (e.g. yawei.ma)")
    p.add_argument("password", help="Plain password (only stored as hash on disk)")
    args = p.parse_args()

    key = args.username.strip().lower()
    if not key:
        print("error: empty username", file=sys.stderr)
        return 1

    header, users, order = _read_entries(_ALLOWED_FILE)
    cred = hash_password(args.password)
    if key not in users:
        order.append(key)
    users[key] = cred
    _write_file(_ALLOWED_FILE, header, users, order)
    print(f"updated {_ALLOWED_FILE}: {key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
