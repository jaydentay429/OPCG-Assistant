"""Read-only recount of daily visitors under the old and new exclusion rules.

Does not write the database and does not invent counts. Callers print only
what these functions return.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from analytics.exclude import (
    REASON_LABELS,
    exclusion_reasons,
    legacy_excluded,
    signals_from_row,
)

HKT = ZoneInfo("Asia/Hong_Kong")

_COMBINED = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[(?P<time>[^\]]+)\] "(?P<method>[A-Z]+) (?P<path>\S+) [^"]*" '
    r'(?P<status>\d+) \S+ "(?P<referrer>[^"]*)" "(?P<ua>[^"]*)"'
)


@dataclass
class DayCount:
    day: str
    old_visitors: int
    new_visitors: int
    excluded_pageviews: int
    by_reason: dict[str, int] = field(default_factory=dict)
    partial: bool = False


@dataclass
class RecountResult:
    days: list[DayCount]
    rows_missing_user_agent: int = 0
    rows_missing_client_ip: int = 0
    skipped_lines: int = 0
    source_note: str = ""


def window_dates(now_hkt: datetime, days: int) -> list[date]:
    if days < 1:
        raise ValueError("days must be >= 1")
    end = now_hkt.date()
    return [end - timedelta(days=offset) for offset in range(days - 1, -1, -1)]


def _day_from_utc_iso(ts: str) -> str | None:
    text = str(ts or "").strip()
    if not text:
        return None
    try:
        dt = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return dt.astimezone(HKT).date().isoformat()


def recount_rows(
    rows: Iterable[Any],
    *,
    days: list[date],
    email_by_user_id: Mapping[int, str] | None = None,
    today: date | None = None,
) -> RecountResult:
    wanted = {item.isoformat() for item in days}
    grouped: dict[str, list[Any]] = defaultdict(list)
    missing_ua = 0
    missing_ip = 0
    for row in rows:
        day = _day_from_utc_iso(str(row["ts"] if _has(row, "ts") else ""))
        if day is None or day not in wanted:
            continue
        grouped[day].append(row)
        if not str(_get(row, "user_agent") or "").strip():
            missing_ua += 1
        if not str(_get(row, "client_ip") or "").strip():
            missing_ip += 1
    out: list[DayCount] = []
    for item in days:
        key = item.isoformat()
        out.append(_count_day(key, grouped.get(key) or [], email_by_user_id, partial=(today == item)))
    return RecountResult(
        days=out,
        rows_missing_user_agent=missing_ua,
        rows_missing_client_ip=missing_ip,
    )


def _count_day(
    day: str,
    rows: list[Any],
    email_by_user_id: Mapping[int, str] | None,
    *,
    partial: bool,
) -> DayCount:
    old_visitors: set[str] = set()
    new_visitors: set[str] = set()
    reasons: Counter[str] = Counter()
    for row in rows:
        signals = signals_from_row(row, email_by_user_id)
        visitor = str(signals.visitor_id or "").strip() or str(signals.ip or "").strip() or "?"
        if not legacy_excluded(signals):
            old_visitors.add(visitor)
        matched = exclusion_reasons(signals)
        if matched:
            reasons[matched[0]] += 1
        else:
            new_visitors.add(visitor)
    return DayCount(
        day=day,
        old_visitors=len(old_visitors),
        new_visitors=len(new_visitors),
        excluded_pageviews=sum(reasons.values()),
        by_reason=dict(reasons),
        partial=partial,
    )


def _has(row: Any, name: str) -> bool:
    keys = getattr(row, "keys", None)
    if callable(keys):
        try:
            return name in set(keys())
        except Exception:
            return False
    if isinstance(row, Mapping):
        return name in row
    return False


def _get(row: Any, name: str) -> Any:
    if not _has(row, name):
        return None
    try:
        return row[name]
    except Exception:
        return None


def read_pageviews(db_path: Path) -> tuple[list[sqlite3.Row], set[str]]:
    """Open sqlite read-only. Raises FileNotFoundError or sqlite3.Error."""
    if not db_path.is_file():
        raise FileNotFoundError(str(db_path))
    uri = db_path.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        cols = {str(row[1]) for row in conn.execute("PRAGMA table_info(pageviews)")}
        if not cols:
            raise sqlite3.Error("pageviews table is missing")
        rows = conn.execute("SELECT * FROM pageviews").fetchall()
        return list(rows), cols
    finally:
        conn.close()


def parse_access_log(text: str) -> tuple[list[dict[str, Any]], int]:
    """Parse combined access-log lines or Caddy JSON lines. Returns (events, skipped)."""
    events: list[dict[str, Any]] = []
    skipped = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        event = _parse_log_line(line)
        if event is None:
            skipped += 1
            continue
        events.append(event)
    return events, skipped


def _parse_log_line(line: str) -> dict[str, Any] | None:
    if line.startswith("{"):
        return _parse_caddy_json(line)
    match = _COMBINED.match(line)
    if not match:
        return None
    when = _parse_combined_time(match.group("time"))
    if when is None:
        return None
    return {
        "ts": when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "visitor_id": match.group("ip"),
        "client_ip": match.group("ip"),
        "user_agent": match.group("ua"),
        "path": match.group("path"),
    }


_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
_COMBINED_TIME = re.compile(
    r"(\d{1,2})/([A-Za-z]{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2}) ([+-])(\d{2})(\d{2})"
)


def _parse_combined_time(text: str) -> datetime | None:
    # 29/Sep/2026:10:00:00 +0800. Month names stay English even if the locale is not.
    match = _COMBINED_TIME.search(text.strip())
    if not match:
        return None
    month = _MONTHS.get(match.group(2).lower())
    if month is None:
        return None
    sign = 1 if match.group(7) == "+" else -1
    offset = timezone(
        timedelta(hours=sign * int(match.group(8)), minutes=sign * int(match.group(9)))
    )
    try:
        return datetime(
            int(match.group(3)),
            month,
            int(match.group(1)),
            int(match.group(4)),
            int(match.group(5)),
            int(match.group(6)),
            tzinfo=offset,
        )
    except ValueError:
        return None


def _parse_caddy_json(line: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    headers = request.get("headers") if isinstance(request.get("headers"), dict) else {}
    ua = _header_value(headers, "User-Agent")
    internal = _header_value(headers, "X-OPCG-Internal")
    ip = str(request.get("client_ip") or request.get("remote_ip") or "").strip()
    ts = _caddy_ts(payload.get("ts"))
    if ts is None or not ip:
        return None
    return {
        "ts": ts,
        "visitor_id": ip,
        "client_ip": ip,
        "user_agent": ua,
        "has_internal_header": 1 if internal.strip() == "1" else 0,
        "path": str(request.get("uri") or "/"),
    }


def _header_value(headers: dict[str, Any], name: str) -> str:
    for key, value in headers.items():
        if str(key).lower() != name.lower():
            continue
        if isinstance(value, list) and value:
            return str(value[0] or "")
        return str(value or "")
    return ""


def _caddy_ts(raw: Any) -> str | None:
    if isinstance(raw, (int, float)):
        try:
            dt = datetime.fromtimestamp(float(raw), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    text = str(raw or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def format_report(result: RecountResult, *, source: str) -> str:
    reason_codes = list(REASON_LABELS)
    header = [
        "日期",
        "旧口径访客",
        "新口径访客",
        "排除浏览",
        *[REASON_LABELS[code] for code in reason_codes],
    ]
    lines = [f"来源: {source}"]
    if result.source_note:
        lines.append(result.source_note)
    lines.append("\t".join(header))
    for day in result.days:
        label = day.day + ("（未结束）" if day.partial else "")
        cells = [
            label,
            str(day.old_visitors),
            str(day.new_visitors),
            str(day.excluded_pageviews),
        ]
        for code in reason_codes:
            cells.append(str(int(day.by_reason.get(code, 0))))
        lines.append("\t".join(cells))
    notes: list[str] = []
    if result.rows_missing_user_agent:
        notes.append(
            f"有 {result.rows_missing_user_agent} 行没有 user_agent，这些行不能按 User-Agent 重算。"
        )
    if result.rows_missing_client_ip:
        notes.append(
            f"有 {result.rows_missing_client_ip} 行没有 client_ip，这些行不能按数据中心 IP 重算。"
        )
    if result.skipped_lines:
        notes.append(f"跳过无法解析的日志 {result.skipped_lines} 行。")
    if notes:
        lines.append("注: " + " ".join(notes))
    lines.append("旧口径只按 visitor_id / username / ip_hash 名单排除。新口径再加上 cookie、账号、User-Agent、数据中心 IP 和内部请求头。")
    return "\n".join(lines) + "\n"
