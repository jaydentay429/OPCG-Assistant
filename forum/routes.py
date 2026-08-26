"""Community forum HTTP routes."""

from __future__ import annotations

import os
from typing import Any, Callable

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field

from forum import db as forum_db

AuthUserFn = Callable[[Request], Any]
OptionalAuthFn = Callable[[Request], Any | None]
UsernameLookupFn = Callable[[str], str | None]
AdminLookupFn = Callable[[str], bool]
EmailLookupFn = Callable[[str], str | None]
EmailFn = Callable[..., None] | None

STAFF_PUBLIC_NAME = "管理员"


class CreateThreadBody(BaseModel):
    category_id: int
    title: str
    body: str
    anonymous: bool = False
    tag_ids: list[int] = Field(default_factory=list)


class CreatePostBody(BaseModel):
    body: str
    anonymous: bool = False
    parent_post_id: int | None = None


class LikeBody(BaseModel):
    target_type: str
    target_id: int
    liked: bool = True


class ReportBody(BaseModel):
    target_type: str
    target_id: int
    reason: str


class AuthorThreadPatch(BaseModel):
    title: str | None = None
    body: str | None = None
    anonymous: bool | None = None


class AuthorPostPatch(BaseModel):
    body: str | None = None
    anonymous: bool | None = None


class AdminThreadPatch(BaseModel):
    pinned: bool | None = None
    locked: bool | None = None
    deleted: bool | None = None


class AdminPostPatch(BaseModel):
    deleted: bool | None = None


class AdminReportPatch(BaseModel):
    status: str
    note: str = ""


class AdminCategoryPatch(BaseModel):
    active: bool


def _owner_id(user_row: Any) -> str:
    return f"user_{int(user_row['id'])}"


def _is_admin(user_row: Any) -> bool:
    try:
        return bool(int(user_row["is_admin"] or 0))
    except (KeyError, TypeError, ValueError):
        return False


def _require_admin(user_row: Any) -> None:
    if not _is_admin(user_row):
        raise HTTPException(status_code=403, detail="需要管理员权限。")


def _public_author(
    *,
    author_user_id: str,
    anonymous: bool,
    viewer_user_id: str | None,
    is_admin_viewer: bool,
    username_lookup: UsernameLookupFn,
    is_admin_lookup: AdminLookupFn | None = None,
) -> dict[str, Any]:
    is_self = bool(viewer_user_id and viewer_user_id == author_user_id)
    reveal = is_admin_viewer or is_self
    is_author_admin = bool(is_admin_lookup(author_user_id)) if is_admin_lookup else False
    if anonymous and not reveal:
        return {
            "anonymous": True,
            "author_display": "anonymous",
            "author_user_id": None,
            "username": None,
            "is_self": is_self,
            "is_author_admin": False,
        }
    uname = username_lookup(author_user_id) or author_user_id
    # Staff posts: public label is「管理员」; real username only for self / admin viewers.
    if is_author_admin and not anonymous:
        return {
            "anonymous": False,
            "author_display": STAFF_PUBLIC_NAME,
            "author_user_id": author_user_id if reveal else author_user_id,
            "username": uname if reveal else STAFF_PUBLIC_NAME,
            "is_self": is_self,
            "is_author_admin": True,
        }
    return {
        "anonymous": bool(anonymous),
        "author_display": uname if not anonymous else "anonymous",
        "author_user_id": author_user_id if reveal else (None if anonymous else author_user_id),
        "username": uname if (reveal or not anonymous) else None,
        "is_self": is_self,
        "is_author_admin": is_author_admin,
    }


def _serialize_thread(
    t: dict[str, Any],
    *,
    viewer_user_id: str | None,
    is_admin_viewer: bool,
    username_lookup: UsernameLookupFn,
    is_admin_lookup: AdminLookupFn | None = None,
    list_mode: bool = False,
) -> dict[str, Any]:
    author = _public_author(
        author_user_id=str(t["author_user_id"]),
        anonymous=bool(int(t.get("anonymous") or 0)),
        viewer_user_id=viewer_user_id,
        is_admin_viewer=is_admin_viewer,
        username_lookup=username_lookup,
        is_admin_lookup=is_admin_lookup,
    )
    out: dict[str, Any] = {
        "id": int(t["id"]),
        "category_id": int(t["category_id"]),
        "title": t["title"],
        "pinned": bool(int(t.get("pinned") or 0)),
        "locked": bool(int(t.get("locked") or 0)),
        "deleted": t.get("deleted_at") is not None,
        "created_at": t["created_at"],
        "updated_at": t["updated_at"],
        "edited_at": t.get("edited_at"),
        "reply_count": int(t.get("reply_count") or 0),
        "like_count": int(t.get("like_count") or 0),
        "liked_by_me": bool(t.get("liked_by_me")),
        "tags": t.get("tags") or [],
        **author,
    }
    if list_mode:
        out["excerpt"] = t.get("excerpt") or forum_db._excerpt(str(t.get("body") or ""))
        out["category_slug"] = t.get("category_slug")
        out["category_title_zh_hant"] = t.get("category_title_zh_hant")
        out["category_title_zh_hans"] = t.get("category_title_zh_hans")
        out["category_title_en"] = t.get("category_title_en")
    else:
        out["body"] = t["body"]
    return out


def _serialize_post(
    p: dict[str, Any],
    *,
    viewer_user_id: str | None,
    is_admin_viewer: bool,
    username_lookup: UsernameLookupFn,
    is_admin_lookup: AdminLookupFn | None = None,
) -> dict[str, Any]:
    author = _public_author(
        author_user_id=str(p["author_user_id"]),
        anonymous=bool(int(p.get("anonymous") or 0)),
        viewer_user_id=viewer_user_id,
        is_admin_viewer=is_admin_viewer,
        username_lookup=username_lookup,
        is_admin_lookup=is_admin_lookup,
    )
    return {
        "id": int(p["id"]),
        "thread_id": int(p["thread_id"]),
        "parent_post_id": int(p["parent_post_id"]) if p.get("parent_post_id") is not None else None,
        "body": p["body"],
        "deleted": p.get("deleted_at") is not None,
        "created_at": p["created_at"],
        "edited_at": p.get("edited_at"),
        "like_count": int(p.get("like_count") or 0),
        "liked_by_me": bool(p.get("liked_by_me")),
        **author,
    }


def _nest_posts(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {p["id"]: {**p, "replies": []} for p in posts}
    roots: list[dict[str, Any]] = []
    for p in posts:
        parent = p.get("parent_post_id")
        node = by_id[p["id"]]
        if parent is None:
            roots.append(node)
        elif parent in by_id:
            by_id[parent]["replies"].append(node)
        else:
            roots.append(node)
    return roots


def _reply_email_enabled() -> bool:
    val = str(os.getenv("COMMUNITY_REPLY_EMAIL") or "on").strip().lower()
    return val not in {"0", "false", "no", "off"}


def _send_reply_notification(
    *,
    thread_author_id: str,
    replier_id: str,
    thread_id: int,
    thread_title: str,
    send_email: EmailFn,
    email_lookup: EmailLookupFn | None,
    site_url: str,
) -> None:
    if not _reply_email_enabled() or not send_email or not email_lookup:
        return
    if thread_author_id == replier_id or not thread_author_id.startswith("user_"):
        return
    to_email = email_lookup(thread_author_id)
    if not to_email:
        return
    link = f"{site_url.rstrip('/')}/community/{thread_id}"
    try:
        send_email(
            to_email,
            f"[OPCG 社区] 你的主题有新回复",
            f"主题「{thread_title}」收到新回复。\n\n查看：{link}\n",
        )
    except Exception as exc:
        print(f"[community-reply] send failed: {exc}")


def mount_forum(
    app: FastAPI,
    *,
    require_auth: AuthUserFn,
    optional_auth: OptionalAuthFn,
    username_lookup: UsernameLookupFn,
    is_admin_lookup: AdminLookupFn | None = None,
    email_lookup: EmailLookupFn | None = None,
    send_email: EmailFn = None,
    site_url: str = "https://optcgassistant.com",
) -> None:
    router = APIRouter(tags=["community"])

    def _ser_thread(*args: Any, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("username_lookup", username_lookup)
        kwargs.setdefault("is_admin_lookup", is_admin_lookup)
        return _serialize_thread(*args, **kwargs)

    def _ser_post(*args: Any, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("username_lookup", username_lookup)
        kwargs.setdefault("is_admin_lookup", is_admin_lookup)
        return _serialize_post(*args, **kwargs)

    def _viewer(request: Request) -> tuple[str | None, bool]:
        row = optional_auth(request)
        if row is None:
            return None, False
        return _owner_id(row), _is_admin(row)

    @router.get("/community/categories")
    def get_categories(request: Request, admin: bool = Query(False)) -> dict[str, Any]:
        include = False
        if admin:
            row = require_auth(request)
            _require_admin(row)
            include = True
        return {"categories": forum_db.list_categories(include_inactive=include)}

    @router.get("/community/tags")
    def get_tags() -> dict[str, Any]:
        return {"tags": forum_db.list_tags()}

    @router.get("/community/threads")
    def get_threads(
        request: Request,
        category_id: int | None = None,
        tag_id: int | None = None,
        q: str | None = None,
        sort: str = Query("new"),
        limit: int = Query(30, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        viewer_id, is_admin = _viewer(request)
        result = forum_db.list_threads(
            category_id=category_id,
            tag_id=tag_id,
            q=q,
            sort=sort,
            limit=limit,
            offset=offset,
            viewer_user_id=viewer_id,
            include_deleted=False,
        )
        return {
            "threads": [
                _ser_thread(
                    t,
                    viewer_user_id=viewer_id,
                    is_admin_viewer=is_admin,
                    username_lookup=username_lookup,
                    list_mode=True,
                )
                for t in result["threads"]
            ],
            "total": result["total"],
            "has_more": result["has_more"],
            "offset": result["offset"],
            "limit": result["limit"],
        }

    @router.get("/community/me/threads")
    def my_threads(
        request: Request,
        limit: int = Query(30, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        user = require_auth(request)
        uid = _owner_id(user)
        result = forum_db.list_threads(
            author_user_id=uid,
            limit=limit,
            offset=offset,
            viewer_user_id=uid,
            include_deleted=False,
        )
        return {
            "threads": [
                _ser_thread(
                    t,
                    viewer_user_id=uid,
                    is_admin_viewer=_is_admin(user),
                    username_lookup=username_lookup,
                    list_mode=True,
                )
                for t in result["threads"]
            ],
            "total": result["total"],
            "has_more": result["has_more"],
            "offset": result["offset"],
            "limit": result["limit"],
        }

    @router.get("/community/me/posts")
    def my_posts(
        request: Request,
        limit: int = Query(30, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        user = require_auth(request)
        uid = _owner_id(user)
        result = forum_db.list_my_posts(author_user_id=uid, limit=limit, offset=offset)
        posts = []
        for p in result["posts"]:
            sp = _ser_post(
                p,
                viewer_user_id=uid,
                is_admin_viewer=_is_admin(user),
                username_lookup=username_lookup,
            )
            sp["thread_title"] = p.get("thread_title")
            posts.append(sp)
        return {
            "posts": posts,
            "total": result["total"],
            "has_more": result["has_more"],
            "offset": result["offset"],
            "limit": result["limit"],
        }

    @router.post("/community/threads")
    def post_thread(request: Request, payload: CreateThreadBody) -> dict[str, Any]:
        user = require_auth(request)
        try:
            created = forum_db.create_thread(
                category_id=payload.category_id,
                author_user_id=_owner_id(user),
                title=payload.title,
                body=payload.body,
                anonymous=payload.anonymous,
                tag_ids=list(payload.tag_ids or []),
                allow_inactive_category=_is_admin(user),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _ser_thread(
            {**created, "liked_by_me": False},
            viewer_user_id=_owner_id(user),
            is_admin_viewer=_is_admin(user),
            username_lookup=username_lookup,
        )

    @router.patch("/community/threads/{thread_id}")
    def patch_thread_author(thread_id: int, request: Request, payload: AuthorThreadPatch) -> dict[str, Any]:
        user = require_auth(request)
        try:
            updated = forum_db.update_thread_by_author(
                thread_id,
                author_user_id=_owner_id(user),
                title=payload.title,
                body=payload.body,
                anonymous=payload.anonymous,
                allow_admin=_is_admin(user),
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        updated["liked_by_me"] = False
        return _ser_thread(
            updated,
            viewer_user_id=_owner_id(user),
            is_admin_viewer=_is_admin(user),
            username_lookup=username_lookup,
        )

    @router.delete("/community/threads/{thread_id}")
    def delete_thread_author(thread_id: int, request: Request) -> dict[str, Any]:
        user = require_auth(request)
        thread = forum_db.get_thread(thread_id, include_deleted=True)
        if thread is None:
            raise HTTPException(status_code=404, detail="主题不存在。")
        if str(thread["author_user_id"]) != _owner_id(user) and not _is_admin(user):
            raise HTTPException(status_code=403, detail="只能删除自己的主题。")
        forum_db.patch_thread(thread_id, deleted=True)
        return {"ok": True}

    @router.get("/community/threads/{thread_id}")
    def get_thread_detail(thread_id: int, request: Request) -> dict[str, Any]:
        viewer_id, is_admin = _viewer(request)
        thread = forum_db.get_thread(thread_id, include_deleted=is_admin)
        if thread is None:
            raise HTTPException(status_code=404, detail="主题不存在。")
        thread["liked_by_me"] = False
        if viewer_id:
            from forum.db import _connect, _lock

            with _lock:
                conn = _connect()
                try:
                    liked = conn.execute(
                        """
                        SELECT 1 FROM likes
                        WHERE user_id = ? AND target_type = 'thread' AND target_id = ?
                        """,
                        (viewer_id, int(thread_id)),
                    ).fetchone()
                    thread["liked_by_me"] = bool(liked)
                finally:
                    conn.close()
        posts_raw = forum_db.list_posts_for_thread(
            thread_id,
            viewer_user_id=viewer_id,
            include_deleted=is_admin,
        )
        posts = [
            _ser_post(
                p,
                viewer_user_id=viewer_id,
                is_admin_viewer=is_admin,
                username_lookup=username_lookup,
            )
            for p in posts_raw
        ]
        return {
            "thread": _ser_thread(
                thread,
                viewer_user_id=viewer_id,
                is_admin_viewer=is_admin,
                username_lookup=username_lookup,
            ),
            "posts": _nest_posts(posts),
        }

    @router.post("/community/threads/{thread_id}/posts")
    def post_reply(thread_id: int, request: Request, payload: CreatePostBody) -> dict[str, Any]:
        user = require_auth(request)
        try:
            created = forum_db.create_post(
                thread_id=thread_id,
                author_user_id=_owner_id(user),
                body=payload.body,
                anonymous=payload.anonymous,
                parent_post_id=payload.parent_post_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _send_reply_notification(
            thread_author_id=str(created.get("_thread_author_user_id") or ""),
            replier_id=_owner_id(user),
            thread_id=thread_id,
            thread_title=str(created.get("_thread_title") or ""),
            send_email=send_email,
            email_lookup=email_lookup,
            site_url=site_url,
        )
        return _ser_post(
            created,
            viewer_user_id=_owner_id(user),
            is_admin_viewer=_is_admin(user),
            username_lookup=username_lookup,
        )

    @router.patch("/community/posts/{post_id}")
    def patch_post_author(post_id: int, request: Request, payload: AuthorPostPatch) -> dict[str, Any]:
        user = require_auth(request)
        try:
            updated = forum_db.update_post_by_author(
                post_id,
                author_user_id=_owner_id(user),
                body=payload.body,
                anonymous=payload.anonymous,
                allow_admin=_is_admin(user),
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _ser_post(
            {**updated, "liked_by_me": False},
            viewer_user_id=_owner_id(user),
            is_admin_viewer=_is_admin(user),
            username_lookup=username_lookup,
        )

    @router.delete("/community/posts/{post_id}")
    def delete_post_author(post_id: int, request: Request) -> dict[str, Any]:
        user = require_auth(request)
        post = forum_db.get_post(post_id, include_deleted=True)
        if post is None:
            raise HTTPException(status_code=404, detail="回复不存在。")
        if str(post["author_user_id"]) != _owner_id(user) and not _is_admin(user):
            raise HTTPException(status_code=403, detail="只能删除自己的回复。")
        forum_db.soft_delete_post(post_id, restore=False)
        return {"ok": True}

    @router.post("/community/likes")
    def like(request: Request, payload: LikeBody) -> dict[str, Any]:
        user = require_auth(request)
        try:
            return forum_db.set_like(
                user_id=_owner_id(user),
                target_type=payload.target_type,
                target_id=payload.target_id,
                liked=bool(payload.liked),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/community/reports")
    def report(request: Request, payload: ReportBody) -> dict[str, Any]:
        user = require_auth(request)
        try:
            created = forum_db.create_report(
                reporter_user_id=_owner_id(user),
                target_type=payload.target_type,
                target_id=payload.target_id,
                reason=payload.reason,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        to_email = str(
            os.getenv("COMMUNITY_REPORT_EMAIL")
            or os.getenv("BUG_REPORT_EMAIL")
            or os.getenv("RANK_APPEAL_EMAIL")
            or ""
        ).strip()
        if to_email and send_email:
            try:
                send_email(
                    to_email,
                    f"[OPCG 社区举报 #{created['id']}] {payload.target_type}:{payload.target_id}",
                    (
                        f"举报编号: {created['id']}\n"
                        f"举报人: {user['username']} ({_owner_id(user)})\n"
                        f"目标: {payload.target_type} #{payload.target_id}\n\n"
                        f"{payload.reason.strip()}\n"
                    ),
                )
            except Exception as exc:
                print(f"[community-report] send failed: {exc}")

        return {"ok": True, "report_id": int(created["id"])}

    # ---- admin ----

    @router.get("/community/admin/reports")
    def admin_reports(
        request: Request,
        status: str | None = Query("open"),
        limit: int = Query(50, ge=1, le=200),
    ) -> dict[str, Any]:
        user = require_auth(request)
        _require_admin(user)
        rows = forum_db.list_reports(status=None if status == "all" else (status or None), limit=limit)
        enriched = []
        for r in rows:
            item = dict(r)
            item["reporter_username"] = username_lookup(str(r["reporter_user_id"]))
            if r["target_type"] == "thread":
                t = forum_db.get_thread(int(r["target_id"]), include_deleted=True)
                if t:
                    item["target_author_user_id"] = t["author_user_id"]
                    item["target_author_username"] = username_lookup(str(t["author_user_id"]))
                    item["target_preview"] = str(t.get("title") or "")[:120]
            else:
                p = forum_db.get_post(int(r["target_id"]), include_deleted=True)
                if p:
                    item["target_author_user_id"] = p["author_user_id"]
                    item["target_author_username"] = username_lookup(str(p["author_user_id"]))
                    item["target_preview"] = str(p.get("body") or "")[:120]
                    item["thread_id"] = p["thread_id"]
            enriched.append(item)
        return {"reports": enriched}

    @router.patch("/community/admin/reports/{report_id}")
    def admin_patch_report(report_id: int, request: Request, payload: AdminReportPatch) -> dict[str, Any]:
        user = require_auth(request)
        _require_admin(user)
        try:
            return forum_db.resolve_report(
                report_id,
                status=payload.status,
                resolver_user_id=_owner_id(user),
                note=payload.note,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.patch("/community/admin/threads/{thread_id}")
    def admin_patch_thread(thread_id: int, request: Request, payload: AdminThreadPatch) -> dict[str, Any]:
        user = require_auth(request)
        _require_admin(user)
        try:
            updated = forum_db.patch_thread(
                thread_id,
                pinned=payload.pinned,
                locked=payload.locked,
                deleted=payload.deleted,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        full = forum_db.get_thread(thread_id, include_deleted=True) or updated
        full["liked_by_me"] = False
        return _ser_thread(
            full,
            viewer_user_id=_owner_id(user),
            is_admin_viewer=True,
            username_lookup=username_lookup,
        )

    @router.patch("/community/admin/posts/{post_id}")
    def admin_patch_post(post_id: int, request: Request, payload: AdminPostPatch) -> dict[str, Any]:
        user = require_auth(request)
        _require_admin(user)
        try:
            if payload.deleted is True:
                updated = forum_db.soft_delete_post(post_id, restore=False)
            elif payload.deleted is False:
                updated = forum_db.soft_delete_post(post_id, restore=True)
            else:
                updated = forum_db.get_post(post_id, include_deleted=True)
                if updated is None:
                    raise ValueError("回复不存在。")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _ser_post(
            {**updated, "liked_by_me": False},
            viewer_user_id=_owner_id(user),
            is_admin_viewer=True,
            username_lookup=username_lookup,
        )

    @router.patch("/community/admin/categories/{category_id}")
    def admin_patch_category(category_id: int, request: Request, payload: AdminCategoryPatch) -> dict[str, Any]:
        user = require_auth(request)
        _require_admin(user)
        try:
            return forum_db.set_category_active(category_id, payload.active)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/community/admin/threads")
    def admin_list_threads(
        request: Request,
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        user = require_auth(request)
        _require_admin(user)
        result = forum_db.list_threads(
            limit=limit,
            offset=offset,
            viewer_user_id=_owner_id(user),
            include_deleted=True,
        )
        return {
            "threads": [
                _ser_thread(
                    t,
                    viewer_user_id=_owner_id(user),
                    is_admin_viewer=True,
                    username_lookup=username_lookup,
                    list_mode=True,
                )
                for t in result["threads"]
            ],
            "total": result["total"],
            "has_more": result["has_more"],
        }

    app.include_router(router)
