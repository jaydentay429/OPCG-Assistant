#!/usr/bin/env python3
"""重置 auth.db 中某个账号的登录密码（交互式输入，不会回显/落盘）。

用法：
    python3 reset_user_password.py --login jaydentay429@gmail.com
    python3 reset_user_password.py --login jaydentay --db /opt/opcg/app/meta/auth.db
"""

from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent / "meta" / "auth.db"
MIN_PASSWORD_LEN = 8


def hash_password(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return base64.b64encode(digest).decode("ascii")


def make_password_hash(password: str) -> str:
    salt = secrets.token_hex(16)
    return f"{salt}${hash_password(password, salt)}"


def main() -> None:
    parser = argparse.ArgumentParser(description="重置账号密码")
    parser.add_argument("--login", required=True, help="邮箱或用户名")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="auth.db 路径")
    parser.add_argument(
        "--revoke-sessions",
        action="store_true",
        help="同时使该账号已有登录态失效",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"找不到数据库：{db_path}")

    login = args.login.strip().lower()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT id, email, username FROM users WHERE email = ? OR username = ? LIMIT 1",
            (login, login),
        ).fetchone()
        if row is None:
            raise SystemExit(f"找不到账号：{args.login}")

        print(f"账号: {row['username']} <{row['email']}>  (id={row['id']})")
        password = getpass.getpass("新密码: ")
        if len(password) < MIN_PASSWORD_LEN:
            raise SystemExit(f"密码至少 {MIN_PASSWORD_LEN} 位。")
        if password != getpass.getpass("再次输入: "):
            raise SystemExit("两次输入不一致。")

        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        conn.execute(
            "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
            (make_password_hash(password), now, int(row["id"])),
        )
        if args.revoke_sessions:
            conn.execute(
                "UPDATE auth_sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                (now, int(row["id"])),
            )
        conn.commit()
    finally:
        conn.close()

    print(f"已更新密码：{db_path}")


if __name__ == "__main__":
    main()
