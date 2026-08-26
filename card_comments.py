"""Per-card comments, likes, and reports (meta/card_comments.db)."""
from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
CARD_COMMENTS_DB = Path(
    os.getenv("CARD_COMMENTS_DB_FILE") or (BASE_DIR / "meta" / "card_comments.db")
)

_lock = threading.Lock()
_initialized = False

BODY_MIN = 2
BODY_MAX = 2000
REASON_MIN = 5
REASON_MAX = 500
RATE_WINDOW_SEC = 60
RATE_MAX_COMMENTS = 8


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _connect() -> sqlite3.Connection:
    CARD_COMMENTS_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CARD_COMMENTS_DB), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_card_comments_db() -> None:
    global _initialized
    if _initialized and CARD_COMMENTS_DB.exists():
        return
    with _lock:
        if _initialized and CARD_COMMENTS_DB.exists():
            return
        conn = _connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS card_comments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    card_base_id TEXT NOT NULL,
                    author_user_id TEXT NOT NULL,
                    author_username TEXT NOT NULL,
                    body TEXT NOT NULL,
                    anonymous INTEGER NOT NULL DEFAULT 0,
                    like_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    edited_at TEXT,
                    deleted_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_card_comments_card
                    ON card_comments(card_base_id, created_at DESC, id DESC);
                CREATE TABLE IF NOT EXISTS card_comment_likes (
                    user_id TEXT NOT NULL,
                    comment_id INTEGER NOT NULL REFERENCES card_comments(id) ON DELETE CASCADE,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, comment_id)
                );
                CREATE TABLE IF NOT EXISTS card_comment_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reporter_user_id TEXT NOT NULL,
                    comment_id INTEGER NOT NULL REFERENCES card_comments(id) ON DELETE CASCADE,
                    reason TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at TEXT NOT NULL,
                    UNIQUE (reporter_user_id, comment_id)
                );
                """
            )
            conn.commit()
        finally:
            conn.close()
        _initialized = True


def _count_recent(conn: sqlite3.Connection, user_id: str) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS n FROM card_comments
        WHERE author_user_id = ?
          AND created_at >= datetime('now', ?)
        """,
        (user_id, f"-{RATE_WINDOW_SEC} seconds"),
    ).fetchone()
    return int(row["n"] if row else 0)


def list_comments(
    *,
    card_base_id: str,
    viewer_user_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    base = str(card_base_id or "").strip().upper()
    if not base:
        return {"comments": [], "total": 0, "offset": 0, "limit": limit}
    limit = max(1, min(100, int(limit)))
    offset = max(0, int(offset))
    init_card_comments_db()
    with _lock:
        conn = _connect()
        try:
            total = int(
                conn.execute(
                    """
                    SELECT COUNT(*) AS n FROM card_comments
                    WHERE card_base_id = ? AND deleted_at IS NULL
                    """,
                    (base,),
                ).fetchone()["n"]
            )
            rows = conn.execute(
                """
                SELECT * FROM card_comments
                WHERE card_base_id = ? AND deleted_at IS NULL
                ORDER BY created_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (base, limit, offset),
            ).fetchall()
            out: list[dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                cid = int(item["id"])
                liked = False
                if viewer_user_id:
                    liked = (
                        conn.execute(
                            """
                            SELECT 1 FROM card_comment_likes
                            WHERE user_id = ? AND comment_id = ?
                            """,
                            (viewer_user_id, cid),
                        ).fetchone()
                        is not None
                    )
                anonymous = bool(item.get("anonymous"))
                author_name = str(item.get("author_username") or "")
                out.append(
                    {
                        "id": cid,
                        "card_base_id": base,
                        "body": item.get("body") or "",
                        "anonymous": anonymous,
                        "author_username": "" if anonymous else author_name,
                        "is_self": bool(viewer_user_id and str(item.get("author_user_id")) == str(viewer_user_id)),
                        "like_count": int(item.get("like_count") or 0),
                        "liked_by_me": liked,
                        "created_at": item.get("created_at") or "",
                        "edited_at": item.get("edited_at") or None,
                    }
                )
            return {"comments": out, "total": total, "offset": offset, "limit": limit}
        finally:
            conn.close()


def create_comment(
    *,
    card_base_id: str,
    author_user_id: str,
    author_username: str,
    body: str,
    anonymous: bool = False,
) -> dict[str, Any]:
    base = str(card_base_id or "").strip().upper()
    uid = str(author_user_id or "").strip()
    username = str(author_username or "").strip() or "user"
    text = str(body or "").strip()
    if not base:
        raise ValueError("缺少卡号。")
    if not uid:
        raise ValueError("需要登录。")
    if len(text) < BODY_MIN or len(text) > BODY_MAX:
        raise ValueError(f"评论长度须为 {BODY_MIN}–{BODY_MAX} 字。")
    init_card_comments_db()
    with _lock:
        conn = _connect()
        try:
            if _count_recent(conn, uid) >= RATE_MAX_COMMENTS:
                raise ValueError("评论太频繁，请稍后再试。")
            cur = conn.execute(
                """
                INSERT INTO card_comments
                (card_base_id, author_user_id, author_username, body, anonymous, like_count, created_at)
                VALUES (?, ?, ?, ?, ?, 0, ?)
                """,
                (base, uid, username, text, 1 if anonymous else 0, _utcnow()),
            )
            conn.commit()
            pid = int(cur.lastrowid)
            row = conn.execute("SELECT * FROM card_comments WHERE id = ?", (pid,)).fetchone()
            item = dict(row)
            return {
                "id": pid,
                "card_base_id": base,
                "body": item.get("body") or "",
                "anonymous": bool(item.get("anonymous")),
                "author_username": "" if item.get("anonymous") else username,
                "is_self": True,
                "like_count": 0,
                "liked_by_me": False,
                "created_at": item.get("created_at") or "",
                "edited_at": None,
            }
        finally:
            conn.close()


def set_comment_like(*, user_id: str, comment_id: int, liked: bool) -> dict[str, Any]:
    uid = str(user_id or "").strip()
    cid = int(comment_id)
    if not uid:
        raise ValueError("需要登录。")
    init_card_comments_db()
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT * FROM card_comments WHERE id = ? AND deleted_at IS NULL",
                (cid,),
            ).fetchone()
            if row is None:
                raise ValueError("评论不存在。")
            existing = conn.execute(
                "SELECT 1 FROM card_comment_likes WHERE user_id = ? AND comment_id = ?",
                (uid, cid),
            ).fetchone()
            if liked and not existing:
                conn.execute(
                    """
                    INSERT INTO card_comment_likes (user_id, comment_id, created_at)
                    VALUES (?, ?, ?)
                    """,
                    (uid, cid, _utcnow()),
                )
                conn.execute(
                    "UPDATE card_comments SET like_count = like_count + 1 WHERE id = ?",
                    (cid,),
                )
            elif not liked and existing:
                conn.execute(
                    "DELETE FROM card_comment_likes WHERE user_id = ? AND comment_id = ?",
                    (uid, cid),
                )
                conn.execute(
                    "UPDATE card_comments SET like_count = MAX(0, like_count - 1) WHERE id = ?",
                    (cid,),
                )
            conn.commit()
            row2 = conn.execute("SELECT like_count FROM card_comments WHERE id = ?", (cid,)).fetchone()
            still = conn.execute(
                "SELECT 1 FROM card_comment_likes WHERE user_id = ? AND comment_id = ?",
                (uid, cid),
            ).fetchone()
            return {
                "comment_id": cid,
                "like_count": int(row2["like_count"] if row2 else 0),
                "liked_by_me": bool(still),
            }
        finally:
            conn.close()


def create_comment_report(*, reporter_user_id: str, comment_id: int, reason: str) -> dict[str, Any]:
    uid = str(reporter_user_id or "").strip()
    cid = int(comment_id)
    text = str(reason or "").strip()
    if not uid:
        raise ValueError("需要登录。")
    if len(text) < REASON_MIN or len(text) > REASON_MAX:
        raise ValueError(f"举报原因长度须为 {REASON_MIN}–{REASON_MAX} 字。")
    init_card_comments_db()
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT * FROM card_comments WHERE id = ? AND deleted_at IS NULL",
                (cid,),
            ).fetchone()
            if row is None:
                raise ValueError("评论不存在。")
            if str(row["author_user_id"]) == uid:
                raise ValueError("不能举报自己的评论。")
            existing = conn.execute(
                """
                SELECT id FROM card_comment_reports
                WHERE reporter_user_id = ? AND comment_id = ?
                """,
                (uid, cid),
            ).fetchone()
            if existing:
                raise ValueError("你已举报过这条评论。")
            cur = conn.execute(
                """
                INSERT INTO card_comment_reports
                (reporter_user_id, comment_id, reason, status, created_at)
                VALUES (?, ?, ?, 'open', ?)
                """,
                (uid, cid, text, _utcnow()),
            )
            conn.commit()
            return {
                "ok": True,
                "report_id": int(cur.lastrowid),
                "comment_id": cid,
                "card_base_id": str(row["card_base_id"] or ""),
                "comment_body": str(row["body"] or "")[:500],
                "comment_author": str(row["author_username"] or ""),
            }
        finally:
            conn.close()


def soft_delete_comment(*, user_id: str, comment_id: int, is_admin: bool = False) -> dict[str, Any]:
    uid = str(user_id or "").strip()
    cid = int(comment_id)
    init_card_comments_db()
    with _lock:
        conn = _connect()
        try:
            row = conn.execute("SELECT * FROM card_comments WHERE id = ?", (cid,)).fetchone()
            if row is None:
                raise ValueError("评论不存在。")
            if not is_admin and str(row["author_user_id"]) != uid:
                raise ValueError("只能删除自己的评论。")
            if row["deleted_at"] is None:
                conn.execute(
                    "UPDATE card_comments SET deleted_at = ? WHERE id = ?",
                    (_utcnow(), cid),
                )
                conn.commit()
            return {"ok": True, "comment_id": cid}
        finally:
            conn.close()
