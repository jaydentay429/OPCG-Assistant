"""Community forum tests."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import forum.db as forum_db


def _temp_db(monkeypatch, tmp_path: Path):
    db = tmp_path / "forum.db"
    monkeypatch.setattr(forum_db, "FORUM_DB_FILE", db)
    forum_db.init_forum_db()
    return db


def test_seed_categories_and_nesting(monkeypatch, tmp_path) -> None:
    _temp_db(monkeypatch, tmp_path)
    cats = forum_db.list_categories()
    assert len(cats) >= 3
    assert all(c.get("slug") != "rules" for c in cats)
    assert all(c.get("slug") != "all" for c in cats)
    admin_cats = forum_db.list_categories(include_inactive=True)
    assert any(c.get("slug") == "all" for c in admin_cats)
    tags = forum_db.list_tags()
    assert len(tags) >= 1
    th = forum_db.create_thread(
        category_id=int(cats[0]["id"]),
        author_user_id="user_1",
        title="t",
        body="body text",
        anonymous=True,
        tag_ids=[int(tags[0]["id"])],
    )
    assert int(th["anonymous"]) == 1
    p1 = forum_db.create_post(
        thread_id=int(th["id"]),
        author_user_id="user_2",
        body="top reply",
        anonymous=False,
    )
    p2 = forum_db.create_post(
        thread_id=int(th["id"]),
        author_user_id="user_1",
        body="nested",
        anonymous=True,
        parent_post_id=int(p1["id"]),
    )
    assert p2["parent_post_id"] == int(p1["id"])
    try:
        forum_db.create_post(
            thread_id=int(th["id"]),
            author_user_id="user_2",
            body="too deep",
            anonymous=False,
            parent_post_id=int(p2["id"]),
        )
        assert False, "expected ValueError"
    except ValueError:
        pass
    liked = forum_db.set_like(
        user_id="user_3",
        target_type="thread",
        target_id=int(th["id"]),
        liked=True,
    )
    assert liked["like_count"] == 1
    rep = forum_db.create_report(
        reporter_user_id="user_3",
        target_type="thread",
        target_id=int(th["id"]),
        reason="spam test",
    )
    assert rep["status"] == "open"
    forum_db.patch_thread(int(th["id"]), pinned=True, locked=True)
    got = forum_db.get_thread(int(th["id"]))
    assert int(got["pinned"]) == 1
    assert int(got["locked"]) == 1


def test_list_threads_search_pagination_and_excerpt(monkeypatch, tmp_path) -> None:
    _temp_db(monkeypatch, tmp_path)
    cats = forum_db.list_categories()
    forum_db.create_thread(
        category_id=int(cats[0]["id"]),
        author_user_id="u1",
        title="Deck help OP14",
        body="Looking for a strong red deck with Luffy leader card.",
        anonymous=False,
        tag_ids=[],
    )
    forum_db.create_thread(
        category_id=int(cats[0]["id"]),
        author_user_id="u2",
        title="Rules question",
        body="How does blocker timing work?",
        anonymous=False,
        tag_ids=[],
    )
    res = forum_db.list_threads(q="Luffy", limit=10, offset=0)
    assert res["total"] == 1
    assert len(res["threads"]) == 1
    assert "Luffy" in res["threads"][0]["title"] or "Luffy" in res["threads"][0].get("excerpt", "")
    assert res["threads"][0].get("category_slug")
    assert res["has_more"] is False


def test_author_edit_and_edit_window(monkeypatch, tmp_path) -> None:
    _temp_db(monkeypatch, tmp_path)
    cats = forum_db.list_categories()
    th = forum_db.create_thread(
        category_id=int(cats[0]["id"]),
        author_user_id="author_1",
        title="original",
        body="body one",
        anonymous=False,
        tag_ids=[],
    )
    updated = forum_db.update_thread_by_author(
        int(th["id"]),
        author_user_id="author_1",
        title="updated title",
    )
    assert updated["title"] == "updated title"
    assert updated.get("edited_at")
    with forum_db._lock:
        conn = forum_db._connect()
        try:
            old = "2000-01-01T00:00:00+00:00"
            conn.execute("UPDATE threads SET created_at = ? WHERE id = ?", (old, int(th["id"])))
            conn.commit()
        finally:
            conn.close()
    try:
        forum_db.update_thread_by_author(int(th["id"]), author_user_id="author_1", title="too late")
        assert False, "expected PermissionError"
    except PermissionError:
        pass


def test_my_posts_and_report_dedupe(monkeypatch, tmp_path) -> None:
    _temp_db(monkeypatch, tmp_path)
    cats = forum_db.list_categories()
    th = forum_db.create_thread(
        category_id=int(cats[0]["id"]),
        author_user_id="me",
        title="mine",
        body="my thread",
        anonymous=True,
        tag_ids=[],
    )
    p = forum_db.create_post(
        thread_id=int(th["id"]),
        author_user_id="me",
        body="my reply",
        anonymous=False,
    )
    mine = forum_db.list_my_posts(author_user_id="me", limit=10, offset=0)
    assert mine["total"] >= 1
    assert any(int(x["id"]) == int(p["id"]) for x in mine["posts"])
    author_threads = forum_db.list_threads(author_user_id="me")
    assert author_threads["total"] >= 1
    forum_db.create_report(
        reporter_user_id="r1",
        target_type="thread",
        target_id=int(th["id"]),
        reason="spam content here",
    )
    try:
        forum_db.create_report(
            reporter_user_id="r1",
            target_type="thread",
            target_id=int(th["id"]),
            reason="duplicate report",
        )
        assert False, "expected duplicate report error"
    except ValueError as exc:
        assert "举报" in str(exc)
