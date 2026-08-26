"""Community forum SQLite store (meta/forum.db)."""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
FORUM_DB_FILE = Path(os.getenv("FORUM_DB_FILE") or (BASE_DIR / "meta" / "forum.db"))
_lock = threading.Lock()

TITLE_MAX = 120
BODY_MAX = 8000
REASON_MAX = 500
REASON_MIN = 5
EDIT_WINDOW_SEC = 24 * 3600
REPORT_DEDUPE_SEC = 24 * 3600
EXCERPT_LEN = 120
RATE_WINDOW_SEC = 60
RATE_MAX_THREADS = 3
RATE_MAX_POSTS = 10

DEFAULT_CATEGORIES = [
    ("all", "全部分區", "全部分区", "All categories", 0),
    ("deckbuilding", "組卡討論", "组卡讨论", "Deckbuilding", 10),
    ("trade", "卡牌／交易", "卡牌/交易", "Cards & Trade", 30),
    ("offtopic", "閒聊", "闲聊", "Off-topic", 40),
]

# Admin-only posting targets: seeded inactive so they never appear in public chips.
ADMIN_ONLY_CATEGORY_SLUGS = frozenset({"all"})


DEFAULT_TAGS = [
    ("deck", "組卡", "组卡", "Deck"),
    ("rules", "規則", "规则", "Rules"),
    ("trade", "交易", "交易", "Trade"),
    ("meta", "環境", "环境", "Meta"),
    ("bug", "Bug", "Bug", "Bug"),
    ("casual", "閒聊", "闲聊", "Casual"),
]


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _connect() -> sqlite3.Connection:
    FORUM_DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(FORUM_DB_FILE), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_forum_db() -> None:
    with _lock:
        conn = _connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slug TEXT NOT NULL UNIQUE,
                    title_zh_hant TEXT NOT NULL,
                    title_zh_hans TEXT NOT NULL,
                    title_en TEXT NOT NULL,
                    sort INTEGER NOT NULL DEFAULT 0,
                    active INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slug TEXT NOT NULL UNIQUE,
                    title_zh_hant TEXT NOT NULL,
                    title_zh_hans TEXT NOT NULL,
                    title_en TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS threads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category_id INTEGER NOT NULL REFERENCES categories(id),
                    author_user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    anonymous INTEGER NOT NULL DEFAULT 0,
                    pinned INTEGER NOT NULL DEFAULT 0,
                    locked INTEGER NOT NULL DEFAULT 0,
                    deleted_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    reply_count INTEGER NOT NULL DEFAULT 0,
                    like_count INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id INTEGER NOT NULL REFERENCES threads(id),
                    parent_post_id INTEGER REFERENCES posts(id),
                    author_user_id TEXT NOT NULL,
                    body TEXT NOT NULL,
                    anonymous INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    deleted_at TEXT,
                    like_count INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS thread_tags (
                    thread_id INTEGER NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
                    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
                    PRIMARY KEY (thread_id, tag_id)
                );
                CREATE TABLE IF NOT EXISTS likes (
                    user_id TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, target_type, target_id)
                );
                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reporter_user_id TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at TEXT NOT NULL,
                    resolved_at TEXT,
                    resolver_user_id TEXT,
                    resolve_note TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_threads_cat_updated
                    ON threads(category_id, pinned DESC, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_posts_thread ON posts(thread_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status, created_at);
                """
            )
            for slug, zh_hant, zh_hans, en, sort in DEFAULT_CATEGORIES:
                active = 0 if slug in ADMIN_ONLY_CATEGORY_SLUGS else 1
                conn.execute(
                    """
                    INSERT OR IGNORE INTO categories
                    (slug, title_zh_hant, title_zh_hans, title_en, sort, active)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (slug, zh_hant, zh_hans, en, sort, active),
                )
            for slug, zh_hant, zh_hans, en in DEFAULT_TAGS:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO tags
                    (slug, title_zh_hant, title_zh_hans, title_en)
                    VALUES (?, ?, ?, ?)
                    """,
                    (slug, zh_hant, zh_hans, en),
                )
            conn.commit()
            _migrate_forum_columns(conn)
            # Remove legacy「規則問答」partition entirely (no threads remain).
            conn.execute("DELETE FROM categories WHERE slug = 'rules'")
            # Admin-only「全部分區」must stay inactive for public chips.
            conn.execute(
                "UPDATE categories SET active = 0, sort = 0, "
                "title_zh_hant = '全部分區', title_zh_hans = '全部分区', title_en = 'All categories' "
                "WHERE slug = 'all'"
            )
            conn.commit()
        finally:
            conn.close()


def _migrate_forum_columns(conn: sqlite3.Connection) -> None:
    for table in ("threads", "posts"):
        cols = {str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if "edited_at" not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN edited_at TEXT")


def _row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def list_categories(*, include_inactive: bool = False) -> list[dict[str, Any]]:
    init_forum_db()
    with _lock:
        conn = _connect()
        try:
            if include_inactive:
                rows = conn.execute(
                    "SELECT * FROM categories ORDER BY sort ASC, id ASC"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM categories WHERE active = 1 AND slug != 'all' "
                    "ORDER BY sort ASC, id ASC"
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def list_tags() -> list[dict[str, Any]]:
    init_forum_db()
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute("SELECT * FROM tags ORDER BY id ASC").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def get_category(category_id: int) -> dict[str, Any] | None:
    init_forum_db()
    with _lock:
        conn = _connect()
        try:
            return _row_dict(
                conn.execute("SELECT * FROM categories WHERE id = ?", (int(category_id),)).fetchone()
            )
        finally:
            conn.close()


def _escape_like(q: str) -> str:
    s = str(q or "").strip()
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _excerpt(body: str, n: int = EXCERPT_LEN) -> str:
    text = " ".join(str(body or "").split())
    if len(text) <= n:
        return text
    return text[: n - 1] + "…"


def _parse_iso(iso: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None


def _within_edit_window(created_at: str) -> bool:
    dt = _parse_iso(created_at)
    if dt is None:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds() <= EDIT_WINDOW_SEC


def _thread_list_where(
    *,
    category_id: int | None,
    tag_id: int | None,
    q: str | None,
    author_user_id: str | None,
    include_deleted: bool,
) -> tuple[str, str, list[Any]]:
    where = ["1=1"]
    params: list[Any] = []
    join = ""
    if tag_id is not None:
        join = "JOIN thread_tags tt ON tt.thread_id = t.id AND tt.tag_id = ?"
        params.append(int(tag_id))
    if not include_deleted:
        where.append("t.deleted_at IS NULL")
    if category_id is not None:
        # Admin「全部分區」posts (slug=all) appear under every category filter.
        where.append(
            "(t.category_id = ? OR t.category_id = "
            "(SELECT id FROM categories WHERE slug = 'all' LIMIT 1))"
        )
        params.append(int(category_id))
    if author_user_id:
        where.append("t.author_user_id = ?")
        params.append(str(author_user_id))
    q_clean = str(q or "").strip().lstrip("#").strip()
    if q_clean:
        # Freeform hashtags live in title/body; "#组卡" and "组卡" both match
        pat = f"%{_escape_like(q_clean)}%"
        where.append("(t.title LIKE ? ESCAPE '\\' OR t.body LIKE ? ESCAPE '\\')")
        params.extend([pat, pat])
    return join, " AND ".join(where), params


def _thread_tags(conn: sqlite3.Connection, thread_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT t.* FROM tags t
        JOIN thread_tags tt ON tt.tag_id = t.id
        WHERE tt.thread_id = ?
        ORDER BY t.id ASC
        """,
        (int(thread_id),),
    ).fetchall()
    return [dict(r) for r in rows]


def _attach_category(conn: sqlite3.Connection, d: dict[str, Any]) -> None:
    cat = conn.execute(
        "SELECT slug, title_zh_hant, title_zh_hans, title_en FROM categories WHERE id = ?",
        (int(d["category_id"]),),
    ).fetchone()
    if cat:
        d["category_slug"] = str(cat["slug"])
        d["category_title_zh_hant"] = str(cat["title_zh_hant"])
        d["category_title_zh_hans"] = str(cat["title_zh_hans"])
        d["category_title_en"] = str(cat["title_en"])
    d["excerpt"] = _excerpt(str(d.get("body") or ""))


def _count_recent(conn: sqlite3.Connection, table: str, user_id: str, window_sec: int) -> int:
    cutoff = datetime.now(timezone.utc).timestamp() - window_sec
    # created_at is ISO; compare lexicographically for UTC Z-less ISO works if consistent
    cutoff_iso = datetime.fromtimestamp(cutoff, tz=timezone.utc).replace(microsecond=0).isoformat()
    row = conn.execute(
        f"SELECT COUNT(*) AS n FROM {table} WHERE author_user_id = ? AND created_at >= ?",
        (user_id, cutoff_iso),
    ).fetchone()
    return int(row["n"] if row else 0)


def create_thread(
    *,
    category_id: int,
    author_user_id: str,
    title: str,
    body: str,
    anonymous: bool,
    tag_ids: list[int],
    allow_inactive_category: bool = False,
) -> dict[str, Any]:
    init_forum_db()
    title = title.strip()
    body = body.strip()
    if not title or len(title) > TITLE_MAX:
        raise ValueError(f"标题长度须为 1–{TITLE_MAX}。")
    if not body or len(body) > BODY_MAX:
        raise ValueError(f"正文长度须为 1–{BODY_MAX}。")
    cat = get_category(category_id)
    if not cat:
        raise ValueError("分区不存在或已关闭。")
    is_admin_only = str(cat.get("slug") or "") in ADMIN_ONLY_CATEGORY_SLUGS
    if is_admin_only and not allow_inactive_category:
        raise ValueError("分区不存在或已关闭。")
    if not int(cat.get("active") or 0) and not allow_inactive_category:
        raise ValueError("分区不存在或已关闭。")
    now = _utcnow()
    with _lock:
        conn = _connect()
        try:
            if _count_recent(conn, "threads", author_user_id, RATE_WINDOW_SEC) >= RATE_MAX_THREADS:
                raise ValueError("发帖过于频繁，请稍后再试。")
            cur = conn.execute(
                """
                INSERT INTO threads
                (category_id, author_user_id, title, body, anonymous, pinned, locked,
                 created_at, updated_at, reply_count, like_count)
                VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?, 0, 0)
                """,
                (
                    int(category_id),
                    author_user_id,
                    title,
                    body,
                    1 if anonymous else 0,
                    now,
                    now,
                ),
            )
            tid = int(cur.lastrowid)
            for tag_id in tag_ids[:8]:
                exists = conn.execute("SELECT id FROM tags WHERE id = ?", (int(tag_id),)).fetchone()
                if exists:
                    conn.execute(
                        "INSERT OR IGNORE INTO thread_tags (thread_id, tag_id) VALUES (?, ?)",
                        (tid, int(tag_id)),
                    )
            conn.commit()
            row = conn.execute("SELECT * FROM threads WHERE id = ?", (tid,)).fetchone()
            out = dict(row)
            out["tags"] = _thread_tags(conn, tid)
            return out
        finally:
            conn.close()


def list_threads(
    *,
    category_id: int | None = None,
    tag_id: int | None = None,
    q: str | None = None,
    author_user_id: str | None = None,
    sort: str = "new",
    limit: int = 30,
    offset: int = 0,
    viewer_user_id: str | None = None,
    include_deleted: bool = False,
) -> dict[str, Any]:
    init_forum_db()
    limit = max(1, min(100, int(limit)))
    offset = max(0, int(offset))
    order = {
        "new": "t.pinned DESC, t.updated_at DESC",
        "hot": "t.pinned DESC, t.like_count DESC, t.reply_count DESC, t.updated_at DESC",
        "pinned": "t.pinned DESC, t.updated_at DESC",
    }.get(sort, "t.pinned DESC, t.updated_at DESC")
    join, where_sql, params = _thread_list_where(
        category_id=category_id,
        tag_id=tag_id,
        q=q,
        author_user_id=author_user_id,
        include_deleted=include_deleted,
    )
    count_sql = f"SELECT COUNT(*) AS n FROM threads t {join} WHERE {where_sql}"
    sql = f"""
        SELECT t.* FROM threads t
        {join}
        WHERE {where_sql}
        ORDER BY {order}
        LIMIT ? OFFSET ?
    """
    with _lock:
        conn = _connect()
        try:
            total_row = conn.execute(count_sql, params).fetchone()
            total = int(total_row["n"] if total_row else 0)
            rows = conn.execute(sql, params + [limit, offset]).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["tags"] = _thread_tags(conn, int(d["id"]))
                _attach_category(conn, d)
                if viewer_user_id:
                    liked = conn.execute(
                        """
                        SELECT 1 FROM likes
                        WHERE user_id = ? AND target_type = 'thread' AND target_id = ?
                        """,
                        (viewer_user_id, int(d["id"])),
                    ).fetchone()
                    d["liked_by_me"] = bool(liked)
                else:
                    d["liked_by_me"] = False
                out.append(d)
            return {
                "threads": out,
                "total": total,
                "has_more": offset + len(out) < total,
                "offset": offset,
                "limit": limit,
            }
        finally:
            conn.close()


def get_thread(thread_id: int, *, include_deleted: bool = False) -> dict[str, Any] | None:
    init_forum_db()
    with _lock:
        conn = _connect()
        try:
            row = conn.execute("SELECT * FROM threads WHERE id = ?", (int(thread_id),)).fetchone()
            if row is None:
                return None
            if row["deleted_at"] is not None and not include_deleted:
                return None
            d = dict(row)
            d["tags"] = _thread_tags(conn, int(thread_id))
            return d
        finally:
            conn.close()


def list_posts_for_thread(
    thread_id: int,
    *,
    viewer_user_id: str | None = None,
    include_deleted: bool = False,
) -> list[dict[str, Any]]:
    init_forum_db()
    with _lock:
        conn = _connect()
        try:
            if include_deleted:
                rows = conn.execute(
                    "SELECT * FROM posts WHERE thread_id = ? ORDER BY created_at ASC, id ASC",
                    (int(thread_id),),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM posts
                    WHERE thread_id = ? AND deleted_at IS NULL
                    ORDER BY created_at ASC, id ASC
                    """,
                    (int(thread_id),),
                ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                if viewer_user_id:
                    liked = conn.execute(
                        """
                        SELECT 1 FROM likes
                        WHERE user_id = ? AND target_type = 'post' AND target_id = ?
                        """,
                        (viewer_user_id, int(d["id"])),
                    ).fetchone()
                    d["liked_by_me"] = bool(liked)
                else:
                    d["liked_by_me"] = False
                out.append(d)
            return out
        finally:
            conn.close()


def create_post(
    *,
    thread_id: int,
    author_user_id: str,
    body: str,
    anonymous: bool,
    parent_post_id: int | None = None,
) -> dict[str, Any]:
    init_forum_db()
    body = body.strip()
    if not body or len(body) > BODY_MAX:
        raise ValueError(f"回复长度须为 1–{BODY_MAX}。")
    with _lock:
        conn = _connect()
        try:
            thread = conn.execute("SELECT * FROM threads WHERE id = ?", (int(thread_id),)).fetchone()
            if thread is None or thread["deleted_at"] is not None:
                raise ValueError("主题不存在。")
            if int(thread["locked"] or 0):
                raise ValueError("主题已锁定，无法回复。")
            parent_id = None
            if parent_post_id is not None:
                parent = conn.execute(
                    "SELECT * FROM posts WHERE id = ? AND thread_id = ?",
                    (int(parent_post_id), int(thread_id)),
                ).fetchone()
                if parent is None or parent["deleted_at"] is not None:
                    raise ValueError("父回复不存在。")
                if parent["parent_post_id"] is not None:
                    raise ValueError("仅支持两级回复，不能再嵌套。")
                parent_id = int(parent["id"])
            if _count_recent(conn, "posts", author_user_id, RATE_WINDOW_SEC) >= RATE_MAX_POSTS:
                raise ValueError("回复过于频繁，请稍后再试。")
            now = _utcnow()
            cur = conn.execute(
                """
                INSERT INTO posts
                (thread_id, parent_post_id, author_user_id, body, anonymous, created_at, like_count)
                VALUES (?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    int(thread_id),
                    parent_id,
                    author_user_id,
                    body,
                    1 if anonymous else 0,
                    now,
                ),
            )
            pid = int(cur.lastrowid)
            conn.execute(
                """
                UPDATE threads
                SET reply_count = reply_count + 1, updated_at = ?
                WHERE id = ?
                """,
                (now, int(thread_id)),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM posts WHERE id = ?", (pid,)).fetchone()
            d = dict(row)
            d["liked_by_me"] = False
            d["_thread_author_user_id"] = str(thread["author_user_id"])
            d["_thread_title"] = str(thread["title"])
            return d
        finally:
            conn.close()


def dismiss_reports_for_target(
    conn: sqlite3.Connection,
    target_type: str,
    target_id: int,
) -> None:
    conn.execute(
        """
        UPDATE reports SET status = 'dismissed', resolved_at = ?, resolve_note = 'auto on delete'
        WHERE target_type = ? AND target_id = ? AND status = 'open'
        """,
        (_utcnow(), target_type, int(target_id)),
    )


def update_thread_by_author(
    thread_id: int,
    *,
    author_user_id: str,
    title: str | None = None,
    body: str | None = None,
    anonymous: bool | None = None,
    allow_admin: bool = False,
) -> dict[str, Any]:
    init_forum_db()
    with _lock:
        conn = _connect()
        try:
            row = conn.execute("SELECT * FROM threads WHERE id = ?", (int(thread_id),)).fetchone()
            if row is None or row["deleted_at"] is not None:
                raise ValueError("主题不存在。")
            if int(row["locked"] or 0):
                raise ValueError("主题已锁定，无法编辑。")
            if str(row["author_user_id"]) != author_user_id and not allow_admin:
                raise PermissionError("只能编辑自己的主题。")
            if not allow_admin and not _within_edit_window(str(row["created_at"])):
                raise PermissionError("已超过 24 小时编辑时限。")
            now = _utcnow()
            if title is not None:
                title = title.strip()
                if not title or len(title) > TITLE_MAX:
                    raise ValueError(f"标题长度须为 1–{TITLE_MAX}。")
                conn.execute("UPDATE threads SET title = ? WHERE id = ?", (title, int(thread_id)))
            if body is not None:
                body = body.strip()
                if not body or len(body) > BODY_MAX:
                    raise ValueError(f"正文长度须为 1–{BODY_MAX}。")
                conn.execute("UPDATE threads SET body = ? WHERE id = ?", (body, int(thread_id)))
            if anonymous is not None:
                conn.execute(
                    "UPDATE threads SET anonymous = ? WHERE id = ?",
                    (1 if anonymous else 0, int(thread_id)),
                )
            if title is not None or body is not None or anonymous is not None:
                conn.execute(
                    "UPDATE threads SET updated_at = ?, edited_at = COALESCE(edited_at, ?) WHERE id = ?",
                    (now, now, int(thread_id)),
                )
            conn.commit()
            out = dict(conn.execute("SELECT * FROM threads WHERE id = ?", (int(thread_id),)).fetchone())
            out["tags"] = _thread_tags(conn, int(thread_id))
            return out
        finally:
            conn.close()


def update_post_by_author(
    post_id: int,
    *,
    author_user_id: str,
    body: str | None = None,
    anonymous: bool | None = None,
    allow_admin: bool = False,
) -> dict[str, Any]:
    init_forum_db()
    with _lock:
        conn = _connect()
        try:
            row = conn.execute("SELECT * FROM posts WHERE id = ?", (int(post_id),)).fetchone()
            if row is None or row["deleted_at"] is not None:
                raise ValueError("回复不存在。")
            thread = conn.execute("SELECT * FROM threads WHERE id = ?", (int(row["thread_id"]),)).fetchone()
            if thread is None or int(thread["locked"] or 0):
                raise ValueError("主题已锁定，无法编辑。")
            if str(row["author_user_id"]) != author_user_id and not allow_admin:
                raise PermissionError("只能编辑自己的回复。")
            if not allow_admin and not _within_edit_window(str(row["created_at"])):
                raise PermissionError("已超过 24 小时编辑时限。")
            now = _utcnow()
            if body is not None:
                body = body.strip()
                if not body or len(body) > BODY_MAX:
                    raise ValueError(f"回复长度须为 1–{BODY_MAX}。")
                conn.execute("UPDATE posts SET body = ? WHERE id = ?", (body, int(post_id)))
            if anonymous is not None:
                conn.execute(
                    "UPDATE posts SET anonymous = ? WHERE id = ?",
                    (1 if anonymous else 0, int(post_id)),
                )
            if body is not None or anonymous is not None:
                conn.execute(
                    "UPDATE posts SET edited_at = COALESCE(edited_at, ?) WHERE id = ?",
                    (now, int(post_id)),
                )
            conn.commit()
            return dict(conn.execute("SELECT * FROM posts WHERE id = ?", (int(post_id),)).fetchone())
        finally:
            conn.close()


def list_my_posts(
    *,
    author_user_id: str,
    limit: int = 30,
    offset: int = 0,
) -> dict[str, Any]:
    init_forum_db()
    limit = max(1, min(100, int(limit)))
    offset = max(0, int(offset))
    with _lock:
        conn = _connect()
        try:
            total_row = conn.execute(
                "SELECT COUNT(*) AS n FROM posts WHERE author_user_id = ? AND deleted_at IS NULL",
                (author_user_id,),
            ).fetchone()
            total = int(total_row["n"] if total_row else 0)
            rows = conn.execute(
                """
                SELECT p.*, t.title AS thread_title
                FROM posts p
                JOIN threads t ON t.id = p.thread_id
                WHERE p.author_user_id = ? AND p.deleted_at IS NULL
                ORDER BY p.created_at DESC
                LIMIT ? OFFSET ?
                """,
                (author_user_id, limit, offset),
            ).fetchall()
            posts = [dict(r) for r in rows]
            return {
                "posts": posts,
                "total": total,
                "has_more": offset + len(posts) < total,
                "offset": offset,
                "limit": limit,
            }
        finally:
            conn.close()


def get_post(post_id: int, *, include_deleted: bool = False) -> dict[str, Any] | None:
    init_forum_db()
    with _lock:
        conn = _connect()
        try:
            row = conn.execute("SELECT * FROM posts WHERE id = ?", (int(post_id),)).fetchone()
            if row is None:
                return None
            if row["deleted_at"] is not None and not include_deleted:
                return None
            return dict(row)
        finally:
            conn.close()


def set_like(*, user_id: str, target_type: str, target_id: int, liked: bool) -> dict[str, Any]:
    if target_type not in {"thread", "post"}:
        raise ValueError("invalid target_type")
    init_forum_db()
    with _lock:
        conn = _connect()
        try:
            table = "threads" if target_type == "thread" else "posts"
            row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (int(target_id),)).fetchone()
            if row is None or row["deleted_at"] is not None:
                raise ValueError("目标不存在。")
            existing = conn.execute(
                """
                SELECT 1 FROM likes
                WHERE user_id = ? AND target_type = ? AND target_id = ?
                """,
                (user_id, target_type, int(target_id)),
            ).fetchone()
            if liked and not existing:
                conn.execute(
                    """
                    INSERT INTO likes (user_id, target_type, target_id, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (user_id, target_type, int(target_id), _utcnow()),
                )
                conn.execute(
                    f"UPDATE {table} SET like_count = like_count + 1 WHERE id = ?",
                    (int(target_id),),
                )
            elif not liked and existing:
                conn.execute(
                    """
                    DELETE FROM likes
                    WHERE user_id = ? AND target_type = ? AND target_id = ?
                    """,
                    (user_id, target_type, int(target_id)),
                )
                conn.execute(
                    f"UPDATE {table} SET like_count = MAX(0, like_count - 1) WHERE id = ?",
                    (int(target_id),),
                )
            conn.commit()
            row2 = conn.execute(f"SELECT like_count FROM {table} WHERE id = ?", (int(target_id),)).fetchone()
            still = conn.execute(
                """
                SELECT 1 FROM likes
                WHERE user_id = ? AND target_type = ? AND target_id = ?
                """,
                (user_id, target_type, int(target_id)),
            ).fetchone()
            return {
                "target_type": target_type,
                "target_id": int(target_id),
                "like_count": int(row2["like_count"] if row2 else 0),
                "liked_by_me": bool(still),
            }
        finally:
            conn.close()


def create_report(
    *,
    reporter_user_id: str,
    target_type: str,
    target_id: int,
    reason: str,
) -> dict[str, Any]:
    if target_type not in {"thread", "post"}:
        raise ValueError("invalid target_type")
    reason = reason.strip()
    if len(reason) < REASON_MIN or len(reason) > REASON_MAX:
        raise ValueError(f"举报原因长度须为 {REASON_MIN}–{REASON_MAX}。")
    init_forum_db()
    with _lock:
        conn = _connect()
        try:
            table = "threads" if target_type == "thread" else "posts"
            row = conn.execute(f"SELECT id FROM {table} WHERE id = ?", (int(target_id),)).fetchone()
            if row is None:
                raise ValueError("目标不存在。")
            cutoff = datetime.now(timezone.utc).timestamp() - REPORT_DEDUPE_SEC
            cutoff_iso = datetime.fromtimestamp(cutoff, tz=timezone.utc).replace(microsecond=0).isoformat()
            dup = conn.execute(
                """
                SELECT id FROM reports
                WHERE reporter_user_id = ? AND target_type = ? AND target_id = ?
                  AND status = 'open' AND created_at >= ?
                """,
                (reporter_user_id, target_type, int(target_id), cutoff_iso),
            ).fetchone()
            if dup:
                raise ValueError("你已举报过该内容，请等待处理。")
            cur = conn.execute(
                """
                INSERT INTO reports
                (reporter_user_id, target_type, target_id, reason, status, created_at)
                VALUES (?, ?, ?, ?, 'open', ?)
                """,
                (reporter_user_id, target_type, int(target_id), reason, _utcnow()),
            )
            rid = int(cur.lastrowid)
            conn.commit()
            return dict(conn.execute("SELECT * FROM reports WHERE id = ?", (rid,)).fetchone())
        finally:
            conn.close()


def list_reports(*, status: str | None = "open", limit: int = 50) -> list[dict[str, Any]]:
    init_forum_db()
    limit = max(1, min(200, int(limit)))
    with _lock:
        conn = _connect()
        try:
            if status:
                rows = conn.execute(
                    """
                    SELECT * FROM reports WHERE status = ?
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM reports ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def resolve_report(
    report_id: int,
    *,
    status: str,
    resolver_user_id: str,
    note: str = "",
) -> dict[str, Any]:
    if status not in {"resolved", "dismissed"}:
        raise ValueError("status must be resolved or dismissed")
    init_forum_db()
    with _lock:
        conn = _connect()
        try:
            row = conn.execute("SELECT * FROM reports WHERE id = ?", (int(report_id),)).fetchone()
            if row is None:
                raise ValueError("举报不存在。")
            conn.execute(
                """
                UPDATE reports
                SET status = ?, resolved_at = ?, resolver_user_id = ?, resolve_note = ?
                WHERE id = ?
                """,
                (status, _utcnow(), resolver_user_id, note.strip()[:500], int(report_id)),
            )
            conn.commit()
            return dict(conn.execute("SELECT * FROM reports WHERE id = ?", (int(report_id),)).fetchone())
        finally:
            conn.close()


def patch_thread(
    thread_id: int,
    *,
    pinned: bool | None = None,
    locked: bool | None = None,
    deleted: bool | None = None,
) -> dict[str, Any]:
    init_forum_db()
    with _lock:
        conn = _connect()
        try:
            row = conn.execute("SELECT * FROM threads WHERE id = ?", (int(thread_id),)).fetchone()
            if row is None:
                raise ValueError("主题不存在。")
            if pinned is not None:
                conn.execute(
                    "UPDATE threads SET pinned = ? WHERE id = ?",
                    (1 if pinned else 0, int(thread_id)),
                )
            if locked is not None:
                conn.execute(
                    "UPDATE threads SET locked = ? WHERE id = ?",
                    (1 if locked else 0, int(thread_id)),
                )
            if deleted is True:
                conn.execute(
                    "UPDATE threads SET deleted_at = ? WHERE id = ?",
                    (_utcnow(), int(thread_id)),
                )
                dismiss_reports_for_target(conn, "thread", int(thread_id))
            elif deleted is False:
                conn.execute("UPDATE threads SET deleted_at = NULL WHERE id = ?", (int(thread_id),))
            conn.commit()
            return dict(conn.execute("SELECT * FROM threads WHERE id = ?", (int(thread_id),)).fetchone())
        finally:
            conn.close()


def soft_delete_post(post_id: int, *, restore: bool = False) -> dict[str, Any]:
    init_forum_db()
    with _lock:
        conn = _connect()
        try:
            row = conn.execute("SELECT * FROM posts WHERE id = ?", (int(post_id),)).fetchone()
            if row is None:
                raise ValueError("回复不存在。")
            if restore:
                if row["deleted_at"] is not None:
                    conn.execute("UPDATE posts SET deleted_at = NULL WHERE id = ?", (int(post_id),))
                    conn.execute(
                        """
                        UPDATE threads SET reply_count = reply_count + 1
                        WHERE id = ?
                        """,
                        (int(row["thread_id"]),),
                    )
            else:
                if row["deleted_at"] is None:
                    conn.execute(
                        "UPDATE posts SET deleted_at = ? WHERE id = ?",
                        (_utcnow(), int(post_id)),
                    )
                    conn.execute(
                        """
                        UPDATE threads SET reply_count = MAX(0, reply_count - 1)
                        WHERE id = ?
                        """,
                        (int(row["thread_id"]),),
                    )
                    dismiss_reports_for_target(conn, "post", int(post_id))
            conn.commit()
            return dict(conn.execute("SELECT * FROM posts WHERE id = ?", (int(post_id),)).fetchone())
        finally:
            conn.close()


def set_category_active(category_id: int, active: bool) -> dict[str, Any]:
    init_forum_db()
    with _lock:
        conn = _connect()
        try:
            row = conn.execute("SELECT * FROM categories WHERE id = ?", (int(category_id),)).fetchone()
            if row is None:
                raise ValueError("分区不存在。")
            if str(row["slug"]) in ADMIN_ONLY_CATEGORY_SLUGS and active:
                raise ValueError("全部分区仅供管理员发帖，不能对公众开放。")
            conn.execute(
                "UPDATE categories SET active = ? WHERE id = ?",
                (1 if active else 0, int(category_id)),
            )
            conn.commit()
            return dict(conn.execute("SELECT * FROM categories WHERE id = ?", (int(category_id),)).fetchone())
        finally:
            conn.close()
