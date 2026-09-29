#!/usr/bin/env python3
"""Recount recent visitors with the new analytics exclusion rules.

Read-only. Prints one row per Hong Kong calendar day. Does not send mail and
does not write the database.

The daily digest is sqlite pageviews (meta/analytics.db on the VPS), not the
Caddy access log. Pass --log only when you want a separate access-log pass:
visitors are client IPs, and cookie/account signals are absent unless the
line carries them.

VPS (after the new columns exist; older rows simply lack UA/IP signals):

  cd /opt/opcg/app && .venv/bin/python scripts/traffic_recount.py \\
    --db /opt/opcg/app/meta/analytics.db \\
    --auth-db /opt/opcg/app/meta/auth.db
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
except ImportError:  # system python without the API venv
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(ROOT / ".env")

from analytics.db import load_user_emails  # noqa: E402
from analytics.recount import (  # noqa: E402
    HKT,
    format_report,
    parse_access_log,
    read_pageviews,
    recount_rows,
    window_dates,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Recount OPCG traffic under the new exclusion rules")
    parser.add_argument("--db", default="", help="sqlite pageviews database (read-only)")
    parser.add_argument("--auth-db", default="", help="optional auth sqlite, read-only, for email lists")
    parser.add_argument("--log", default="", help="combined access log or Caddy JSON log")
    parser.add_argument("--days", type=int, default=7, help="Hong Kong calendar days, ending today (default 7)")
    args = parser.parse_args(argv)

    if args.db and args.log:
        print("请只指定 --db 或 --log 其中一个。", file=sys.stderr)
        return 2
    if args.days < 1:
        print("--days 至少为 1。", file=sys.stderr)
        return 2

    now = datetime.now(HKT)
    days = window_dates(now, args.days)
    auth_path = Path(args.auth_db).expanduser() if args.auth_db else None

    if args.log:
        log_path = Path(args.log).expanduser()
        if not log_path.is_file():
            print(f"找不到日志：{log_path}", file=sys.stderr)
            print("没有输出访客数字。", file=sys.stderr)
            return 2
        events, skipped = parse_access_log(log_path.read_text(encoding="utf-8", errors="replace"))
        result = recount_rows(events, days=days, today=now.date())
        result.skipped_lines = skipped
        result.source_note = (
            "这是访问日志口径：访客按客户端 IP 计，不是日报里的 visitor_id。"
            "合并日志通常没有 cookie 和登录账号。"
        )
        sys.stdout.write(format_report(result, source=f"log {log_path}"))
        return 0

    if args.db:
        db_path = Path(args.db).expanduser()
    else:
        from analytics.db import analytics_db_path

        db_path = analytics_db_path()

    if not db_path.is_file():
        print(f"找不到统计库：{db_path}", file=sys.stderr)
        print("仓库和 CI 里没有线上 pageviews。没有输出访客数字。", file=sys.stderr)
        print(
            "在 VPS 上执行：cd /opt/opcg/app && .venv/bin/python scripts/traffic_recount.py "
            "--db /opt/opcg/app/meta/analytics.db --auth-db /opt/opcg/app/meta/auth.db",
            file=sys.stderr,
        )
        return 2

    try:
        rows, columns = read_pageviews(db_path)
    except Exception as exc:
        print(f"无法只读打开统计库：{exc}", file=sys.stderr)
        print("没有输出访客数字。", file=sys.stderr)
        return 2

    if auth_path is None:
        sibling = db_path.parent / "auth.db"
        auth_path = sibling if sibling.is_file() else (ROOT / "meta" / "auth.db")
    emails = load_user_emails(auth_path) if auth_path.is_file() else {}
    result = recount_rows(rows, days=days, email_by_user_id=emails, today=now.date())
    notes = []
    if "user_agent" not in columns:
        notes.append("统计库还没有 user_agent 列，User-Agent 规则对已有行无效。")
    if "client_ip" not in columns:
        notes.append("统计库还没有 client_ip 列，数据中心 IP 规则对已有行无效。")
    if not emails:
        notes.append("没有读到账号邮箱。ANALYTICS_EXCLUDE_EMAILS 只作用于已经写入 email 列的行。")
    if notes:
        result.source_note = " ".join(notes)
    sys.stdout.write(format_report(result, source=f"sqlite {db_path}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
