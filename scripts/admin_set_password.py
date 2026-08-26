#!/usr/bin/env python3
"""Set a user's password in production auth.db (run on the VPS).

  cd /opt/opcg/app
  .venv/bin/python scripts/admin_set_password.py EMAIL NEW_PASSWORD
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTH_DB = ROOT / "meta" / "auth.db"


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: admin_set_password.py EMAIL NEW_PASSWORD", file=sys.stderr)
        return 2
    email = str(sys.argv[1] or "").strip().lower()
    password = str(sys.argv[2] or "")
    if "@" not in email:
        print("invalid email", file=sys.stderr)
        return 2
    if len(password) < 8:
        print("password must be at least 8 characters", file=sys.stderr)
        return 2
    if not AUTH_DB.is_file():
        print(f"missing {AUTH_DB}", file=sys.stderr)
        return 1
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    password_hash = f"{salt}${base64.b64encode(digest).decode('ascii')}"
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(AUTH_DB)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT id, email, username FROM users WHERE email = ?", (email,)).fetchone()
        if row is None:
            print(f"no user with email {email}", file=sys.stderr)
            return 1
        conn.execute(
            "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
            (password_hash, now, int(row["id"])),
        )
        conn.commit()
        print(f"updated password for {row['username']} <{row['email']}>")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
