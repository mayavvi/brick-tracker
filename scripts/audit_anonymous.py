#!/usr/bin/env python3
"""Audit and optionally clean up anonymous/legacy rows in tracker.db.

Usage:
    python scripts/audit_anonymous.py                  # show counts only
    python scripts/audit_anonymous.py --export         # export anonymous rows to JSON
    python scripts/audit_anonymous.py --delete         # delete anonymous rows (ask for confirm)
    python scripts/audit_anonymous.py --db path/to/db  # custom DB path
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "tracker.db"
ANONYMOUS_NAMES = ("anonymous",)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit anonymous rows in tracker.db")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Path to tracker.db")
    parser.add_argument("--export", action="store_true", help="Export anonymous rows to JSON")
    parser.add_argument("--delete", action="store_true", help="Delete anonymous rows after confirmation")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"[ERROR] Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row

    placeholders = ",".join("?" * len(ANONYMOUS_NAMES))

    users_rows = con.execute(
        f"SELECT * FROM users WHERE username IN ({placeholders})", ANONYMOUS_NAMES
    ).fetchall()
    prefs_rows = con.execute(
        f"SELECT * FROM user_preferences WHERE username IN ({placeholders})", ANONYMOUS_NAMES
    ).fetchall()
    tasks_rows = con.execute(
        f"SELECT * FROM custom_tasks WHERE owner IN ({placeholders})", ANONYMOUS_NAMES
    ).fetchall()

    print(f"DB: {db_path}")
    print(f"  users rows with anonymous username:          {len(users_rows)}")
    print(f"  user_preferences rows with anonymous owner:  {len(prefs_rows)}")
    print(f"  custom_tasks rows with anonymous owner:      {len(tasks_rows)}")
    total = len(users_rows) + len(prefs_rows) + len(tasks_rows)
    if total == 0:
        print("[OK] No anonymous rows found.")
        return

    if args.export:
        out = {
            "users": [dict(r) for r in users_rows],
            "user_preferences": [dict(r) for r in prefs_rows],
            "custom_tasks": [dict(r) for r in tasks_rows],
        }
        export_path = db_path.parent / "anonymous_export.json"
        export_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[EXPORT] Saved to {export_path}")

    if args.delete:
        confirm = input(f"\nDelete {total} anonymous rows? This cannot be undone. Type 'yes' to confirm: ")
        if confirm.strip().lower() != "yes":
            print("Aborted.")
            return
        con.execute(f"DELETE FROM custom_tasks WHERE owner IN ({placeholders})", ANONYMOUS_NAMES)
        con.execute(f"DELETE FROM user_preferences WHERE username IN ({placeholders})", ANONYMOUS_NAMES)
        con.execute(f"DELETE FROM users WHERE username IN ({placeholders})", ANONYMOUS_NAMES)
        con.commit()
        print(f"[DONE] Deleted {total} rows.")

    con.close()


if __name__ == "__main__":
    main()
