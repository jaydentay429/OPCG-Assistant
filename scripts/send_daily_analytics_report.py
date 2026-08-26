#!/usr/bin/env python3
"""Send yesterday's (HKT) analytics digest email. Safe to run from cron."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from analytics.db import init_analytics_db  # noqa: E402
from analytics.report import build_daily_report  # noqa: E402
from email_util import EmailSendError, send_email  # noqa: E402


def _send_email(to_email: str, subject: str, body: str) -> None:
    try:
        send_email(to_email, subject, body, log_prefix="analytics")
    except EmailSendError as exc:
        print(f"[analytics] send failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Send OPCG daily analytics email")
    parser.add_argument(
        "--day",
        help="HKT calendar day YYYY-MM-DD (default: yesterday HKT)",
        default="",
    )
    parser.add_argument(
        "--to",
        help="Override ANALYTICS_REPORT_EMAIL",
        default="",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print report only, do not send",
    )
    args = parser.parse_args()

    init_analytics_db()
    day: date | None = None
    if args.day.strip():
        day = date.fromisoformat(args.day.strip())

    subject, body = build_daily_report(day)
    to_email = (
        str(args.to or "").strip()
        or str(os.getenv("ANALYTICS_REPORT_EMAIL") or "").strip()
        or str(os.getenv("SMTP_USER") or "").strip()
    )
    if not to_email:
        print("[analytics] No ANALYTICS_REPORT_EMAIL / SMTP_USER — abort", file=sys.stderr)
        print(subject)
        print(body)
        return 2

    print(f"[analytics] {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} report ready → {to_email}")
    if args.dry_run:
        print(subject)
        print(body)
        return 0

    _send_email(to_email, subject, body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
