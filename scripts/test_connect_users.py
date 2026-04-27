#!/usr/bin/env python3
"""Quick diagnostic for Posit Connect user API.

This script verifies whether the Posit Python SDK can list users from the
Connect server and optionally filter by username.

Examples:
    python scripts/test_connect_users.py
    python scripts/test_connect_users.py --limit 50
    python scripts/test_connect_users.py --username alice
    python scripts/test_connect_users.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


def _obj_to_dict(obj: Any) -> dict[str, Any]:
    """Convert SDK model objects to plain dict for display."""
    if isinstance(obj, dict):
        return obj

    for method_name in ("model_dump", "dict", "to_dict"):
        method = getattr(obj, method_name, None)
        if callable(method):
            try:
                data = method()
                if isinstance(data, dict):
                    return data
            except Exception:
                pass

    data: dict[str, Any] = {}
    for key in dir(obj):
        if key.startswith("_"):
            continue
        try:
            value = getattr(obj, key)
        except Exception:
            continue
        if callable(value):
            continue
        if isinstance(value, (str, int, float, bool, type(None))):
            data[key] = value
    return data


def _print_table(rows: list[dict[str, Any]]) -> None:
    cols = [
        "guid",
        "username",
        "email",
        "first_name",
        "last_name",
        "user_role",
        "confirmed",
        "locked",
        "active_time",
    ]
    existing_cols = [c for c in cols if any(c in row for row in rows)]
    if not existing_cols:
        existing_cols = sorted({k for row in rows for k in row.keys()})

    widths = {c: max(len(c), *(len(str(row.get(c, ""))) for row in rows)) for c in existing_cols}

    header = " | ".join(c.ljust(widths[c]) for c in existing_cols)
    sep = "-+-".join("-" * widths[c] for c in existing_cols)
    print(header)
    print(sep)
    for row in rows:
        print(" | ".join(str(row.get(c, "")).ljust(widths[c]) for c in existing_cols))


def main() -> None:
    parser = argparse.ArgumentParser(description="Test Posit Connect users API access")
    parser.add_argument("--limit", type=int, default=20, help="Max users to show")
    parser.add_argument("--username", default="", help="Filter by exact username")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of table")
    args = parser.parse_args()

    try:
        from posit import connect
    except Exception as exc:
        print(
            "[ERROR] Cannot import 'posit.connect'. Install dependency first:\n"
            "  pip install rsconnect-python\n"
            f"Import error: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        client = connect.Client()
        users = client.users.find()
    except Exception as exc:
        print(
            "[ERROR] Failed to query Connect users API.\n"
            "Check CONNECT_SERVER / CONNECT_API_KEY (or equivalent credential setup).",
            file=sys.stderr,
        )
        print(f"Details: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(3)

    rows = [_obj_to_dict(u) for u in users]

    if args.username:
        rows = [r for r in rows if str(r.get("username", "")) == args.username]

    rows = rows[: max(args.limit, 0)]

    print(f"[INFO] users returned: {len(users)}")
    print(f"[INFO] users after filter/limit: {len(rows)}")

    if not rows:
        print("[WARN] No matching users.")
        return

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        _print_table(rows)


if __name__ == "__main__":
    main()
