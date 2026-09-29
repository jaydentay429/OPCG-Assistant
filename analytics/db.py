from __future__ import annotations

import hashlib
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from analytics.exclude import TrafficSignals, exclusion_reasons, ip_is_datacenter

BASE_DIR = Path(__file__).resolve().parent.parent
_lock = threading.Lock()


def analytics_db_path() -> Path:
    raw = str(os.getenv("ANALYTICS_DB_FILE") or "").strip()
    return Path(raw) if raw else (BASE_DIR / "meta" / "analytics.db")


def analytics_enabled() -> bool:
    raw = str(os.getenv("ANALYTICS_ENABLED", "1")).strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _connect() -> sqlite3.Connection:
    path = analytics_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_analytics_db() -> None:
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pageviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    path TEXT NOT NULL,
                    referrer TEXT,
                    visitor_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    user_id INTEGER,
                    username TEXT,
                    ip_hash TEXT,
                    ua_hash TEXT,
                    language TEXT,
                    screen TEXT,
                    is_excluded INTEGER NOT NULL DEFAULT 0,
                    user_agent TEXT,
                    has_exclude_cookie INTEGER NOT NULL DEFAULT 0,
                    has_internal_header INTEGER NOT NULL DEFAULT 0,
                    ip_is_datacenter INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_pv_ts ON pageviews(ts)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_pv_visitor_ts ON pageviews(visitor_id, ts)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_pv_path_ts ON pageviews(path, ts)"
            )
            _ensure_pageview_columns(conn)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ai_crawl_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    bot TEXT NOT NULL,
                    path TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ai_crawl_ts ON ai_crawl_logs(ts)"
            )
            conn.commit()
        finally:
            conn.close()


def _ensure_pageview_columns(conn: sqlite3.Connection) -> None:
    """Add signal columns. Do not add email or client_ip; those are not stored."""
    have = {str(row[1]) for row in conn.execute("PRAGMA table_info(pageviews)")}
    additions = (
        ("user_agent", "TEXT"),
        ("has_exclude_cookie", "INTEGER NOT NULL DEFAULT 0"),
        ("has_internal_header", "INTEGER NOT NULL DEFAULT 0"),
        ("ip_is_datacenter", "INTEGER NOT NULL DEFAULT 0"),
    )
    for name, ddl in additions:
        if name not in have:
            conn.execute(f"ALTER TABLE pageviews ADD COLUMN {name} {ddl}")


def load_user_emails(auth_db: Path | None = None) -> dict[int, str]:
    """Read-only id → email map. Pageviews do not store the address."""
    path = auth_db or (BASE_DIR / "meta" / "auth.db")
    if not path.is_file():
        return {}
    uri = path.resolve().as_uri() + "?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.Error:
        return {}
    try:
        rows = conn.execute("SELECT id, email FROM users").fetchall()
    except sqlite3.Error:
        return {}
    finally:
        conn.close()
    out: dict[int, str] = {}
    for row in rows:
        try:
            uid = int(row[0])
        except (TypeError, ValueError):
            continue
        email = str(row[1] or "").strip()
        if email:
            out[uid] = email
    return out


def hash_ip(ip: str | None) -> str | None:
    ip = (ip or "").strip()
    if not ip or ip in {"127.0.0.1", "::1"}:
        # Still hash localhost so local testing is countable but not raw.
        ip = ip or "unknown"
    salt = str(os.getenv("ANALYTICS_IP_SALT") or "opcg-analytics-v1").strip()
    return hashlib.sha256(f"{salt}|{ip}".encode("utf-8")).hexdigest()[:16]


def hash_ua(ua: str | None) -> str | None:
    ua = (ua or "").strip()
    if not ua:
        return None
    return hashlib.sha256(ua.encode("utf-8")).hexdigest()[:12]


def insert_pageview(
    *,
    path: str,
    visitor_id: str,
    session_id: str,
    referrer: str | None = None,
    user_id: int | None = None,
    username: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    language: str | None = None,
    screen: str | None = None,
    ts: datetime | None = None,
    email: str | None = None,
    exclude_cookie: bool = False,
    internal_header: bool = False,
) -> dict[str, Any]:
    path = (path or "/").strip()[:300] or "/"
    # Persist without query/hash so reports stay aggregatable.
    path = path.split("?", 1)[0].split("#", 1)[0].strip()[:300] or "/"
    if not path.startswith("/"):
        path = "/" + path
    visitor_id = (visitor_id or "").strip()[:64]
    session_id = (session_id or "").strip()[:64]
    if not visitor_id or not session_id:
        raise ValueError("visitor_id and session_id are required")

    when = ts or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    ts_s = when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    ip_h = hash_ip(ip)
    ua_h = hash_ua(user_agent)
    ua_stored = (user_agent or "").strip()[:300] or None
    email_now = (email or "").strip()[:200] or None
    cookie_flag = 1 if exclude_cookie else 0
    header_flag = 1 if internal_header else 0
    datacenter_flag = 1 if ip_is_datacenter(ip) else 0
    excluded = (
        1
        if exclusion_reasons(
            TrafficSignals(
                visitor_id=visitor_id,
                username=username,
                email=email_now,
                user_id=user_id,
                ip_hash=ip_h,
                ip_is_datacenter=bool(datacenter_flag),
                user_agent=ua_stored,
                exclude_cookie=bool(exclude_cookie),
                internal_header=bool(internal_header),
            )
        )
        else 0
    )

    with _lock:
        conn = _connect()
        try:
            cur = conn.execute(
                """
                INSERT INTO pageviews (
                    ts, path, referrer, visitor_id, session_id,
                    user_id, username, ip_hash, ua_hash, language, screen, is_excluded,
                    user_agent, has_exclude_cookie, has_internal_header, ip_is_datacenter
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts_s,
                    path,
                    (referrer or "")[:500] or None,
                    visitor_id,
                    session_id,
                    user_id,
                    (username or None),
                    ip_h,
                    ua_h,
                    (language or None),
                    (screen or None),
                    excluded,
                    ua_stored,
                    cookie_flag,
                    header_flag,
                    datacenter_flag,
                ),
            )
            conn.commit()
            row_id = int(cur.lastrowid or 0)
        finally:
            conn.close()

    return {
        "id": row_id,
        "ts": ts_s,
        "is_excluded": bool(excluded),
        "visitor_id": visitor_id,
        "ip_hash": ip_h,
    }


def insert_ai_crawl(*, bot: str, path: str, ts: datetime | None = None) -> None:
    """Record an AI / citation crawler hit. No cookies, no identity."""
    bot_s = (bot or "").strip()[:64]
    path_s = (path or "/").strip()[:300] or "/"
    path_s = path_s.split("?", 1)[0].split("#", 1)[0].strip()[:300] or "/"
    if not path_s.startswith("/"):
        path_s = "/" + path_s
    if not bot_s:
        return
    when = ts or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    ts_s = when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO ai_crawl_logs (ts, bot, path) VALUES (?, ?, ?)",
                (ts_s, bot_s, path_s),
            )
            conn.commit()
        finally:
            conn.close()


# Columns the report is allowed to read. email and client_ip are never selected,
# even if an older database still has those columns.
PAGEVIEW_READ_COLUMNS = (
    "id",
    "ts",
    "path",
    "referrer",
    "visitor_id",
    "session_id",
    "user_id",
    "username",
    "ip_hash",
    "ua_hash",
    "language",
    "screen",
    "is_excluded",
    "user_agent",
    "has_exclude_cookie",
    "has_internal_header",
    "ip_is_datacenter",
)


def pageview_select_list(have: set[str]) -> str:
    cols = [name for name in PAGEVIEW_READ_COLUMNS if name in have]
    if "ts" not in cols or "visitor_id" not in cols:
        raise sqlite3.Error("pageviews is missing required columns")
    return ", ".join(cols)


def fetch_pageviews(
    start_utc: str,
    end_utc: str,
    *,
    include_excluded: bool = True,
) -> list[sqlite3.Row]:
    """Inclusive start, exclusive end. ISO-ish UTC strings comparable lexicographically."""
    with _lock:
        conn = _connect()
        try:
            have = {str(row[1]) for row in conn.execute("PRAGMA table_info(pageviews)")}
            selected = pageview_select_list(have)
            where = "ts >= ? AND ts < ?"
            if not include_excluded:
                where += " AND is_excluded = 0"
            rows = conn.execute(
                f"""
                SELECT {selected} FROM pageviews
                WHERE {where}
                ORDER BY ts ASC
                """,
                (start_utc, end_utc),
            ).fetchall()
            return list(rows)
        finally:
            conn.close()


def first_seen_before(visitor_ids: set[str], before_ts: str) -> set[str]:
    """Return visitor_ids that already appeared before before_ts."""
    if not visitor_ids:
        return set()
    with _lock:
        conn = _connect()
        try:
            found: set[str] = set()
            # Chunk IN clauses
            ids = list(visitor_ids)
            for i in range(0, len(ids), 400):
                chunk = ids[i : i + 400]
                placeholders = ",".join("?" * len(chunk))
                rows = conn.execute(
                    f"""
                    SELECT DISTINCT visitor_id FROM pageviews
                    WHERE visitor_id IN ({placeholders}) AND ts < ?
                    """,
                    (*chunk, before_ts),
                ).fetchall()
                found.update(str(r["visitor_id"]) for r in rows)
            return found
        finally:
            conn.close()
