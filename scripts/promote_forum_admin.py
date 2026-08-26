#!/usr/bin/env python3
"""Promote a registered user to community admin (is_admin=1).

Usage:
  python scripts/promote_forum_admin.py --username YOUR_NAME
  # or
  python scripts/promote_forum_admin.py --email you@example.com
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTH_DB = Path(__import__("os").getenv("AUTH_DB_FILE") or (ROOT / "meta" / "auth.db"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--username", default="")
    ap.add_argument("--email", default="")
    ap.add_argument("--revoke", action="store_true", help="Clear is_admin instead")
    args = ap.parse_args()
    if not args.username and not args.email:
        print("Provide --username or --email", file=sys.stderr)
        return 2
    if not AUTH_DB.is_file():
        print(f"auth.db not found: {AUTH_DB}", file=sys.stderr)
        return 1
    conn = sqlite3.connect(str(AUTH_DB))
    conn.row_factory = sqlite3.Row
    try:
        cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "is_admin" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
            conn.commit()
        if args.username:
            row = conn.execute(
                "SELECT id, username, email, is_admin FROM users WHERE username = ?",
                (args.username,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id, username, email, is_admin FROM users WHERE email = ?",
                (args.email.lower().strip(),),
            ).fetchone()
        if row is None:
            print("User not found.", file=sys.stderr)
            return 1
        flag = 0 if args.revoke else 1
        conn.execute("UPDATE users SET is_admin = ? WHERE id = ?", (flag, int(row["id"])))
        conn.commit()
        print(f"OK user_id={row['id']} username={row['username']} is_admin={flag}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
