from __future__ import annotations

import hashlib
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
ANALYTICS_DB_FILE = Path(os.getenv("ANALYTICS_DB_FILE") or (BASE_DIR / "meta" / "analytics.db"))
_lock = threading.Lock()


def analytics_enabled() -> bool:
    raw = str(os.getenv("ANALYTICS_ENABLED", "1")).strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _connect() -> sqlite3.Connection:
    ANALYTICS_DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(ANALYTICS_DB_FILE), timeout=30)
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
                    is_excluded INTEGER NOT NULL DEFAULT 0
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
            conn.commit()
        finally:
            conn.close()


def _csv_set(env_key: str) -> set[str]:
    raw = str(os.getenv(env_key) or "").strip()
    if not raw:
        return set()
    return {x.strip() for x in raw.split(",") if x.strip()}


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


def is_excluded_event(
    *,
    visitor_id: str,
    username: str | None,
    ip_hash: str | None,
) -> bool:
    """Match against current ANALYTICS_EXCLUDE_* env lists (exact, stripped)."""
    vid = (visitor_id or "").strip()
    if vid and vid in _csv_set("ANALYTICS_EXCLUDE_VISITOR_IDS"):
        return True
    uname = (username or "").strip()
    if uname:
        excluded_names = _csv_set("ANALYTICS_EXCLUDE_USERNAMES")
        if uname in excluded_names or uname.lower() in {x.lower() for x in excluded_names}:
            return True
    iph = (ip_hash or "").strip()
    if iph and iph in _csv_set("ANALYTICS_EXCLUDE_IP_HASHES"):
        return True
    return False


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
    excluded = 1 if is_excluded_event(visitor_id=visitor_id, username=username, ip_hash=ip_h) else 0

    with _lock:
        conn = _connect()
        try:
            cur = conn.execute(
                """
                INSERT INTO pageviews (
                    ts, path, referrer, visitor_id, session_id,
                    user_id, username, ip_hash, ua_hash, language, screen, is_excluded
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            if include_excluded:
                rows = conn.execute(
                    """
                    SELECT * FROM pageviews
                    WHERE ts >= ? AND ts < ?
                    ORDER BY ts ASC
                    """,
                    (start_utc, end_utc),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM pageviews
                    WHERE ts >= ? AND ts < ? AND is_excluded = 0
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
