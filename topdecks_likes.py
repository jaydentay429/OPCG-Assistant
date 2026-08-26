"""Tournament deck likes (meta/topdecks_likes.db)."""
from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
TOPDECKS_LIKES_DB = Path(
    os.getenv("TOPDECKS_LIKES_DB_FILE") or (BASE_DIR / "meta" / "topdecks_likes.db")
)

_lock = threading.Lock()
_initialized = False


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _connect() -> sqlite3.Connection:
    TOPDECKS_LIKES_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(TOPDECKS_LIKES_DB), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_topdecks_likes_db() -> None:
    global _initialized
    if _initialized and TOPDECKS_LIKES_DB.exists():
        return
    with _lock:
        if _initialized and TOPDECKS_LIKES_DB.exists():
            return
        conn = _connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS topdeck_likes (
                    user_id TEXT NOT NULL,
                    deck_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, deck_id)
                );
                CREATE INDEX IF NOT EXISTS idx_topdeck_likes_deck
                    ON topdeck_likes(deck_id);
                """
            )
            conn.commit()
        finally:
            conn.close()
        _initialized = True


def like_counts_for(deck_ids: list[str]) -> dict[str, int]:
    """Return {deck_id: count} for the given ids (missing → 0 omitted)."""
    ids = [str(x).strip() for x in deck_ids if str(x).strip()]
    if not ids:
        return {}
    init_topdecks_likes_db()
    with _lock:
        conn = _connect()
        try:
            out: dict[str, int] = {}
            # SQLite variable limit — chunk
            chunk = 400
            for i in range(0, len(ids), chunk):
                part = ids[i : i + chunk]
                placeholders = ",".join("?" * len(part))
                rows = conn.execute(
                    f"""
                    SELECT deck_id, COUNT(*) AS n
                    FROM topdeck_likes
                    WHERE deck_id IN ({placeholders})
                    GROUP BY deck_id
                    """,
                    part,
                ).fetchall()
                for row in rows:
                    out[str(row["deck_id"])] = int(row["n"] or 0)
            return out
        finally:
            conn.close()


def liked_set_for_user(user_id: str, deck_ids: list[str]) -> set[str]:
    uid = str(user_id or "").strip()
    ids = [str(x).strip() for x in deck_ids if str(x).strip()]
    if not uid or not ids:
        return set()
    init_topdecks_likes_db()
    with _lock:
        conn = _connect()
        try:
            liked: set[str] = set()
            chunk = 400
            for i in range(0, len(ids), chunk):
                part = ids[i : i + chunk]
                placeholders = ",".join("?" * len(part))
                rows = conn.execute(
                    f"""
                    SELECT deck_id FROM topdeck_likes
                    WHERE user_id = ? AND deck_id IN ({placeholders})
                    """,
                    [uid, *part],
                ).fetchall()
                for row in rows:
                    liked.add(str(row["deck_id"]))
            return liked
        finally:
            conn.close()


def attach_likes(
    items: list[dict[str, Any]],
    *,
    user_id: str | None = None,
) -> list[dict[str, Any]]:
    ids = [str(it.get("id") or "").strip() for it in items if isinstance(it, dict)]
    counts = like_counts_for(ids)
    liked = liked_set_for_user(user_id or "", ids) if user_id else set()
    for it in items:
        if not isinstance(it, dict):
            continue
        did = str(it.get("id") or "").strip()
        it["like_count"] = int(counts.get(did) or 0)
        it["liked_by_me"] = did in liked
    return items


def set_like(*, user_id: str, deck_id: str, liked: bool) -> dict[str, Any]:
    uid = str(user_id or "").strip()
    did = str(deck_id or "").strip()
    if not uid:
        raise ValueError("需要登录。")
    if not did:
        raise ValueError("缺少卡组 id。")
    init_topdecks_likes_db()
    with _lock:
        conn = _connect()
        try:
            existing = conn.execute(
                "SELECT 1 FROM topdeck_likes WHERE user_id = ? AND deck_id = ?",
                (uid, did),
            ).fetchone()
            if liked and not existing:
                conn.execute(
                    """
                    INSERT INTO topdeck_likes (user_id, deck_id, created_at)
                    VALUES (?, ?, ?)
                    """,
                    (uid, did, _utcnow()),
                )
            elif not liked and existing:
                conn.execute(
                    "DELETE FROM topdeck_likes WHERE user_id = ? AND deck_id = ?",
                    (uid, did),
                )
            conn.commit()
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM topdeck_likes WHERE deck_id = ?",
                (did,),
            ).fetchone()
            still = conn.execute(
                "SELECT 1 FROM topdeck_likes WHERE user_id = ? AND deck_id = ?",
                (uid, did),
            ).fetchone()
            return {
                "deck_id": did,
                "like_count": int(row["n"] if row else 0),
                "liked_by_me": bool(still),
            }
        finally:
            conn.close()
