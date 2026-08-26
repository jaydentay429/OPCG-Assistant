"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  createCommunityPost,
  createCommunityThread,
  deleteCommunityPost,
  deleteCommunityThread,
  fetchCommunityCategories,
  fetchCommunityThread,
  fetchCommunityThreads,
  likeCommunity,
  patchCommunityAdminPost,
  patchCommunityAdminThread,
  patchCommunityPost,
  patchCommunityThread,
  reportCommunity,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatRelativeTime } from "@/lib/formatRelativeTime";
import { useI18n } from "@/lib/i18n";
import type { CommunityCategory, CommunityPost, CommunityThread } from "@/lib/types";
import { isSearchCommitKey } from "../SearchBar";
import { ConfirmDialog } from "./ConfirmDialog";
import { isCommunityRulesThread, localizeCommunityRulesThread } from "./communityRulesI18n";
import { catTitle, categoryClass, displayName } from "./communityUtils";

const PAGE_SIZE = 30;
const TITLE_MAX = 120;
const BODY_MAX = 8000;

/** Extract freeform #tags from text for list display. */
function extractHashtags(text: string): string[] {
  const found = text.match(/#[\w\u3400-\u9fff\u3040-\u30ff]+/g) || [];
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of found) {
    const key = raw.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(raw);
    if (out.length >= 6) break;
  }
  return out;
}

function ListSkeleton() {
  return (
    <ul className="community-thread-list">
      {Array.from({ length: 5 }).map((_, i) => (
        <li key={i} className="community-skeleton community-skeleton-card" />
      ))}
    </ul>
  );
}

function DetailSkeleton() {
  return (
    <div className="community-page">
      <div className="community-skeleton community-skeleton-line" style={{ width: "40%" }} />
      <div className="community-skeleton community-skeleton-block" style={{ height: 120, marginTop: 12 }} />
      <div className="community-skeleton community-skeleton-block" style={{ height: 80, marginTop: 16 }} />
    </div>
  );
}

function isEditExpiredError(err: unknown): boolean {
  if (!(err instanceof Error)) return false;
  const m = err.message.toLowerCase();
  return m.includes("403") || m.includes("24") || m.includes("编辑") || m.includes("編輯") || m.includes("edit");
}

export function CommunityHome() {
  const { t, lang } = useI18n();
  const { token, isLoggedIn, isAdmin, requestLogin } = useAuth();
  const [categories, setCategories] = useState<CommunityCategory[]>([]);
  const [threads, setThreads] = useState<CommunityThread[]>([]);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [offset, setOffset] = useState(0);
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [sort, setSort] = useState("new");
  const [searchInput, setSearchInput] = useState("");
  const [searchQ, setSearchQ] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setSearchQ(searchInput.trim()), 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const hasFilter = Boolean(searchQ || categoryId != null);

  const loadPage = useCallback(
    (nextOffset: number, append: boolean) => {
      if (append) setLoadingMore(true);
      else setLoading(true);
      setError(null);
      return fetchCommunityThreads({
        token,
        category_id: categoryId,
        q: searchQ || null,
        sort,
        limit: PAGE_SIZE,
        offset: nextOffset,
      })
        .then((res) => {
          setThreads((prev) => (append ? [...prev, ...res.threads] : res.threads));
          setTotal(res.total);
          setHasMore(res.has_more);
          setOffset(nextOffset);
        })
        .catch((e) => setError(e instanceof Error ? e.message : String(e)))
        .finally(() => {
          setLoading(false);
          setLoadingMore(false);
        });
    },
    [token, categoryId, searchQ, sort],
  );

  useEffect(() => {
    void loadPage(0, false);
  }, [loadPage]);

  useEffect(() => {
    fetchCommunityCategories({ token })
      .then(setCategories)
      .catch(() => setCategories([]));
  }, [token]);

  function clearFilters() {
    setSearchInput("");
    setSearchQ("");
    setCategoryId(null);
  }

  return (
    <div className="community-page">
      <header className="community-header">
        <div>
          <h1>{t("community.title")}</h1>
          <p className="muted">{t("community.subtitle")}</p>
        </div>
        <div className="community-header-actions">
          {isLoggedIn ? (
            <Link href="/community/me" className="community-nav-btn">
              {t("community.my_posts")}
            </Link>
          ) : null}
          {isAdmin ? (
            <Link href="/community/admin" className="community-nav-btn">
              {t("community.admin")}
            </Link>
          ) : null}
          {isLoggedIn ? (
            <Link href="/community/new" className="btn-primary-link">
              {t("community.new_thread")}
            </Link>
          ) : (
            <button type="button" onClick={() => requestLogin()}>
              {t("community.login_to_post")}
            </button>
          )}
        </div>
      </header>

      <form
        className="community-search"
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          setSearchQ(searchInput.trim());
        }}
      >
        <input
          type="search"
          name="q"
          enterKeyHint="search"
          autoComplete="off"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          onKeyDown={(e) => {
            if (!isSearchCommitKey(e)) return;
            e.preventDefault();
            setSearchQ(searchInput.trim());
            e.currentTarget.blur();
          }}
          onSearch={(e) => {
            e.preventDefault();
            setSearchQ(searchInput.trim());
            e.currentTarget.blur();
          }}
          placeholder={t("community.search_placeholder")}
          aria-label={t("community.search_placeholder")}
        />
        <button type="submit" className="search-submit-btn">
          {t("search.submit")}
        </button>
      </form>

      <div className="community-filters">
        <div className="community-chips">
          <button
            type="button"
            className={categoryId == null ? "is-active" : "secondary"}
            onClick={() => setCategoryId(null)}
          >
            {t("community.all_categories")}
          </button>
          {categories.map((c) => (
            <button
              key={c.id}
              type="button"
              className={categoryId === c.id ? "is-active" : "secondary"}
              onClick={() => setCategoryId(c.id)}
            >
              {catTitle(c, lang)}
            </button>
          ))}
        </div>
        <div className="community-sort">
          <label>
            {t("community.sort")}
            <select value={sort} onChange={(e) => setSort(e.target.value)}>
              <option value="new">{t("community.sort_new")}</option>
              <option value="hot">{t("community.sort_hot")}</option>
            </select>
          </label>
        </div>
      </div>

      {!loading && total > 0 ? <p className="muted community-total">{t("community.total_n", { n: total })}</p> : null}
      {error ? <p className="error-text">{error}</p> : null}
      {loading ? <ListSkeleton /> : null}
      {!loading && !threads.length ? (
        <div className="community-empty">
          <p className="muted">{hasFilter ? t("community.empty_filtered") : t("community.empty")}</p>
          {hasFilter ? (
            <button type="button" className="secondary" onClick={clearFilters}>
              {t("community.clear_filters")}
            </button>
          ) : null}
        </div>
      ) : null}

      {!loading && threads.length ? (
        <ul className="community-thread-list">
          {threads.map((raw) => {
            const th = localizeCommunityRulesThread(raw, lang);
            return (
            <li
              key={th.id}
              className={`${th.pinned ? "is-pinned" : ""} ${categoryClass(th.category_slug)}`.trim()}
            >
              <Link href={`/community/${th.id}`}>
                <div className="community-thread-meta">
                  {th.category_slug ? (
                    <span className="community-cat-label">{catTitle(th, lang)}</span>
                  ) : null}
                  {th.pinned ? <span className="community-badge">{t("community.pinned")}</span> : null}
                  {th.locked ? <span className="community-badge is-lock">{t("community.locked")}</span> : null}
                  <span className="muted">{displayName(th, t)}</span>
                  <span className="muted">· {formatRelativeTime(th.updated_at, lang, t)}</span>
                </div>
                <strong className="community-thread-title">{th.title}</strong>
                {th.excerpt ? <p className="community-thread-excerpt muted">{th.excerpt}</p> : null}
                <div className="community-thread-stats muted">
                  {extractHashtags(`${th.title} ${th.excerpt || ""}`).map((tag) => (
                    <span key={tag} className="community-hash-tag">
                      {tag}{" "}
                    </span>
                  ))}
                  <span>
                    {t("community.replies_n", { n: th.reply_count })} · {t("community.likes_n", { n: th.like_count })}
                  </span>
                </div>
              </Link>
            </li>
            );
          })}
        </ul>
      ) : null}

      {hasMore ? (
        <div className="community-load-more">
          <button type="button" className="secondary" disabled={loadingMore} onClick={() => void loadPage(offset + PAGE_SIZE, true)}>
            {loadingMore ? t("community.loading") : t("community.load_more")}
          </button>
        </div>
      ) : null}
    </div>
  );
}

export function CommunityNewThread() {
  const { t, lang } = useI18n();
  const router = useRouter();
  const { token, isLoggedIn, isAdmin, requestLogin } = useAuth();
  const [categories, setCategories] = useState<CommunityCategory[]>([]);
  const [categoryId, setCategoryId] = useState<number | "">("");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [anonymous, setAnonymous] = useState(false);
  const [preview, setPreview] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setCategories([]);
      return;
    }
    fetchCommunityCategories({ token, admin: isAdmin })
      .then((rows) => {
        const sorted = [...rows].sort((a, b) => {
          if (a.slug === "all") return -1;
          if (b.slug === "all") return 1;
          return (a.sort ?? 0) - (b.sort ?? 0);
        });
        setCategories(sorted);
      })
      .catch(() => setCategories([]));
  }, [token, isAdmin]);

  if (!isLoggedIn || !token) {
    return (
      <div className="community-page">
        <p>{t("community.login_to_post")}</p>
        <button type="button" onClick={() => requestLogin()}>
          {t("auth.login")}
        </button>
        <p>
          <Link href="/community" className="community-nav-btn">
            {t("community.back")}
          </Link>
        </p>
      </div>
    );
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!token || categoryId === "") return;
    setBusy(true);
    setError(null);
    try {
      const th = await createCommunityThread(token, {
        category_id: Number(categoryId),
        title,
        body,
        anonymous,
      });
      router.push(`/community/${th.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  }

  return (
    <div className="community-page">
      <p className="community-back-row">
        <Link href="/community" className="community-nav-btn">
          {t("community.back")}
        </Link>
      </p>
      <h1>{t("community.new_thread")}</h1>
      <form className="community-form" onSubmit={(e) => void submit(e)}>
        <label>
          {t("community.category")}
          <select
            required
            value={categoryId}
            onChange={(e) => setCategoryId(e.target.value ? Number(e.target.value) : "")}
          >
            <option value="">{t("community.pick_category")}</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {catTitle(c, lang)}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("community.thread_title")}
          <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={TITLE_MAX} required />
          <span className="muted community-char-count">{t("community.chars_n", { n: title.length, max: TITLE_MAX })}</span>
        </label>
        <div className="community-compose-toolbar">
          <button type="button" className={preview ? "secondary" : "is-active"} onClick={() => setPreview(false)}>
            {t("community.compose")}
          </button>
          <button type="button" className={preview ? "is-active" : "secondary"} onClick={() => setPreview(true)}>
            {t("community.preview")}
          </button>
        </div>
        {preview ? (
          <div className="community-preview community-post-body">{body || "—"}</div>
        ) : (
          <label>
            {t("community.thread_body")}
            <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={10} maxLength={BODY_MAX} required />
            <span className="muted community-char-count">{t("community.chars_n", { n: body.length, max: BODY_MAX })}</span>
          </label>
        )}
        <p className="muted community-hashtag-hint">{t("community.hashtag_hint")}</p>
        <label className="community-check">
          <input type="checkbox" checked={anonymous} onChange={(e) => setAnonymous(e.target.checked)} />
          {t("community.post_anonymous")}
        </label>
        {error ? <p className="error-text">{error}</p> : null}
        <button type="submit" disabled={busy}>
          {busy ? t("community.submitting") : t("community.submit")}
        </button>
      </form>
    </div>
  );
}

function ReportBox({
  targetType,
  targetId,
  onDone,
}: {
  targetType: "thread" | "post";
  targetId: number;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const { token, requestLogin, isLoggedIn } = useAuth();
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function submit() {
    if (!isLoggedIn || !token) {
      requestLogin();
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      await reportCommunity(token, { target_type: targetType, target_id: targetId, reason });
      setMsg(t("community.report_sent"));
      setReason("");
      onDone();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="community-report-box">
      <textarea
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder={t("community.report_placeholder")}
        rows={3}
        maxLength={500}
      />
      <button type="button" className="secondary" disabled={busy || reason.trim().length < 5} onClick={() => void submit()}>
        {t("community.report_submit")}
      </button>
      {msg ? <p className="muted">{msg}</p> : null}
    </div>
  );
}

function PostNode({
  post,
  threadId,
  locked,
  onRefresh,
  onLikeUpdate,
  depth = 0,
}: {
  post: CommunityPost;
  threadId: number;
  locked: boolean;
  onRefresh: () => void;
  onLikeUpdate: (postId: number, likeCount: number, liked: boolean) => void;
  depth?: number;
}) {
  const { t, lang } = useI18n();
  const { token, isLoggedIn, isAdmin, requestLogin } = useAuth();
  const [replyOpen, setReplyOpen] = useState(false);
  const [reportConfirm, setReportConfirm] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [editBody, setEditBody] = useState(post.body);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [body, setBody] = useState("");
  const [anonymous, setAnonymous] = useState(false);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  async function toggleLike() {
    if (!token) {
      requestLogin();
      return;
    }
    const prevCount = post.like_count;
    const prevLiked = post.liked_by_me;
    const nextLiked = !prevLiked;
    onLikeUpdate(post.id, prevCount + (nextLiked ? 1 : -1), nextLiked);
    try {
      const res = await likeCommunity(token, "post", post.id, nextLiked);
      onLikeUpdate(post.id, res.like_count, res.liked_by_me);
    } catch {
      onLikeUpdate(post.id, prevCount, prevLiked);
    }
  }

  async function sendReply() {
    if (!token) {
      requestLogin();
      return;
    }
    setBusy(true);
    try {
      await createCommunityPost(token, threadId, {
        body,
        anonymous,
        parent_post_id: depth === 0 ? post.id : post.parent_post_id || post.id,
      });
      setBody("");
      setReplyOpen(false);
      onRefresh();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function saveEdit() {
    if (!token) return;
    setBusy(true);
    setActionError(null);
    try {
      await patchCommunityPost(token, post.id, { body: editBody });
      setEditOpen(false);
      onRefresh();
    } catch (e) {
      setActionError(isEditExpiredError(e) ? t("community.edit_window_expired") : e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function confirmDelete() {
    if (!token) return;
    setBusy(true);
    try {
      await deleteCommunityPost(token, post.id);
      setDeleteConfirm(false);
      onRefresh();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function softDelete(del: boolean) {
    if (!token) return;
    await patchCommunityAdminPost(token, post.id, { deleted: del });
    onRefresh();
  }

  if (post.deleted && !isAdmin && !post.is_self) return null;

  return (
    <div id={`post-${post.id}`} className={`community-post ${depth ? "is-nested" : ""} ${post.deleted ? "is-deleted" : ""}`}>
      <div className="community-post-meta">
        <strong>{displayName(post, t)}</strong>
        <span className="muted">{formatRelativeTime(post.created_at, lang, t)}</span>
        {post.edited_at ? <span className="muted">({t("community.edited")})</span> : null}
        {post.deleted ? <span className="community-badge">{t("community.deleted")}</span> : null}
      </div>
      {editOpen ? (
        <div className="community-edit-box">
          <textarea value={editBody} onChange={(e) => setEditBody(e.target.value)} rows={4} maxLength={BODY_MAX} />
          <div className="community-post-actions">
            <button type="button" disabled={busy} onClick={() => void saveEdit()}>
              {t("community.save")}
            </button>
            <button type="button" className="secondary" onClick={() => setEditOpen(false)}>
              {t("community.cancel")}
            </button>
          </div>
        </div>
      ) : (
        <p className="community-post-body">{post.body}</p>
      )}
      <div className="community-post-actions">
        <button type="button" className="ghost community-touch-btn" onClick={() => void toggleLike()}>
          {post.liked_by_me ? "♥" : "♡"} {post.like_count}
        </button>
        {!locked && depth === 0 ? (
          <button type="button" className="ghost community-touch-btn" onClick={() => setReplyOpen((v) => !v)}>
            {t("community.reply")}
          </button>
        ) : null}
        <button
          type="button"
          className="ghost community-touch-btn"
          onClick={() => {
            if (reportOpen) {
              setReportOpen(false);
              setReportConfirm(false);
            } else {
              setReportConfirm(true);
            }
          }}
        >
          {t("community.report")}
        </button>
        {post.is_self && !post.deleted ? (
          <>
            <button type="button" className="ghost community-touch-btn" onClick={() => { setEditBody(post.body); setEditOpen(true); }}>
              {t("community.edit")}
            </button>
            <button type="button" className="ghost community-touch-btn" onClick={() => setDeleteConfirm(true)}>
              {t("community.delete")}
            </button>
          </>
        ) : null}
        {isAdmin ? (
          <button type="button" className="ghost community-touch-btn" onClick={() => void softDelete(!post.deleted)}>
            {post.deleted ? t("community.restore") : t("community.delete")}
          </button>
        ) : null}
      </div>
      {actionError ? <p className="error-text">{actionError}</p> : null}
      <ConfirmDialog
        open={reportConfirm}
        title={t("community.confirm_title")}
        message={t("community.report_confirm")}
        confirmLabel={t("community.confirm_ok")}
        cancelLabel={t("community.confirm_cancel")}
        onConfirm={() => {
          setReportConfirm(false);
          setReportOpen(true);
        }}
        onCancel={() => setReportConfirm(false)}
      />
      <ConfirmDialog
        open={deleteConfirm}
        title={t("community.confirm_title")}
        message={t("community.delete_confirm")}
        confirmLabel={t("community.confirm_ok")}
        cancelLabel={t("community.confirm_cancel")}
        danger
        onConfirm={() => void confirmDelete()}
        onCancel={() => setDeleteConfirm(false)}
      />
      {reportOpen ? (
        <ReportBox targetType="post" targetId={post.id} onDone={() => setReportOpen(false)} />
      ) : null}
      {replyOpen ? (
        <div className="community-reply-box">
          <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={3} maxLength={BODY_MAX} />
          <label className="community-check">
            <input type="checkbox" checked={anonymous} onChange={(e) => setAnonymous(e.target.checked)} />
            {t("community.post_anonymous")}
          </label>
          <button type="button" disabled={busy || !body.trim()} onClick={() => void sendReply()}>
            {t("community.submit_reply")}
          </button>
        </div>
      ) : null}
      {(post.replies || []).map((r) => (
        <PostNode
          key={r.id}
          post={r}
          threadId={threadId}
          locked={locked}
          onRefresh={onRefresh}
          onLikeUpdate={onLikeUpdate}
          depth={depth + 1}
        />
      ))}
    </div>
  );
}

export function CommunityThreadDetail({ threadId }: { threadId: number }) {
  const { t, lang } = useI18n();
  const router = useRouter();
  const { token, isLoggedIn, isAdmin, requestLogin } = useAuth();
  const [thread, setThread] = useState<CommunityThread | null>(null);
  const [posts, setPosts] = useState<CommunityPost[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [body, setBody] = useState("");
  const [anonymous, setAnonymous] = useState(false);
  const [busy, setBusy] = useState(false);
  const [reportConfirm, setReportConfirm] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editBody, setEditBody] = useState("");
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const titleSet = useRef(false);

  const reload = useCallback(() => {
    setLoading(true);
    return fetchCommunityThread(threadId, token)
      .then((data) => {
        setThread(data.thread);
        setPosts(data.posts);
        setEditTitle(data.thread.title);
        setEditBody(data.thread.body || "");
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [threadId, token]);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    if (!thread) return;
    const title = localizeCommunityRulesThread(thread, lang).title;
    document.title = `${title} · ${t("community.title")}`;
    titleSet.current = true;
    return () => {
      if (titleSet.current) document.title = t("community.title");
    };
  }, [thread, lang, t]);

  function patchPostLike(postId: number, likeCount: number, liked: boolean) {
    setPosts((prev) => {
      const walk = (items: CommunityPost[]): CommunityPost[] =>
        items.map((p) => {
          if (p.id === postId) return { ...p, like_count: likeCount, liked_by_me: liked };
          if (p.replies?.length) return { ...p, replies: walk(p.replies) };
          return p;
        });
      return walk(prev);
    });
  }

  async function toggleLike() {
    if (!token || !thread) {
      requestLogin();
      return;
    }
    const prevCount = thread.like_count;
    const prevLiked = thread.liked_by_me;
    const nextLiked = !prevLiked;
    setThread({ ...thread, like_count: prevCount + (nextLiked ? 1 : -1), liked_by_me: nextLiked });
    try {
      const res = await likeCommunity(token, "thread", thread.id, nextLiked);
      setThread((th) => (th ? { ...th, like_count: res.like_count, liked_by_me: res.liked_by_me } : th));
    } catch {
      setThread((th) => (th ? { ...th, like_count: prevCount, liked_by_me: prevLiked } : th));
    }
  }

  async function submitReply(e: React.FormEvent) {
    e.preventDefault();
    if (!token) {
      requestLogin();
      return;
    }
    setBusy(true);
    setActionError(null);
    try {
      await createCommunityPost(token, threadId, { body, anonymous });
      setBody("");
      await reload();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function saveThreadEdit() {
    if (!token) return;
    setBusy(true);
    setActionError(null);
    try {
      await patchCommunityThread(token, threadId, { title: editTitle, body: editBody });
      setEditOpen(false);
      await reload();
    } catch (e) {
      setActionError(isEditExpiredError(e) ? t("community.edit_window_expired") : e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function confirmDeleteThread() {
    if (!token) return;
    setBusy(true);
    try {
      await deleteCommunityThread(token, threadId);
      router.push("/community");
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  async function adminPatch(patch: { pinned?: boolean; locked?: boolean; deleted?: boolean }) {
    if (!token) return;
    await patchCommunityAdminThread(token, threadId, patch);
    await reload();
  }

  if (loading && !thread) return <DetailSkeleton />;

  if (error && !thread) {
    return (
      <div className="community-page">
        <p className="error-text">{error}</p>
        <Link href="/community" className="community-nav-btn">
          {t("community.back")}
        </Link>
      </div>
    );
  }
  if (!thread) return null;

  const view = localizeCommunityRulesThread(thread, lang);
  const isRules = isCommunityRulesThread(thread);

  return (
    <div className="community-page">
      {thread.locked ? (
        <div className="community-locked-banner" role="status">
          {t("community.locked_banner")}
        </div>
      ) : null}
      <p className="community-back-row">
        <Link href="/community" className="community-nav-btn">
          {t("community.back")}
        </Link>
      </p>
      <article className="community-thread-detail">
        <div className="community-thread-meta">
          {thread.pinned ? <span className="community-badge">{t("community.pinned")}</span> : null}
          {thread.locked ? <span className="community-badge is-lock">{t("community.locked")}</span> : null}
          <span>{displayName(thread, t)}</span>
          <span className="muted">· {formatRelativeTime(thread.created_at, lang, t)}</span>
          {thread.edited_at ? <span className="muted">({t("community.edited")})</span> : null}
        </div>
        {editOpen && !isRules ? (
          <div className="community-edit-box">
            <input value={editTitle} onChange={(e) => setEditTitle(e.target.value)} maxLength={TITLE_MAX} />
            <textarea value={editBody} onChange={(e) => setEditBody(e.target.value)} rows={8} maxLength={BODY_MAX} />
            <div className="community-post-actions">
              <button type="button" disabled={busy} onClick={() => void saveThreadEdit()}>
                {t("community.save")}
              </button>
              <button type="button" className="secondary" onClick={() => setEditOpen(false)}>
                {t("community.cancel")}
              </button>
            </div>
          </div>
        ) : (
          <>
            <h1>{view.title}</h1>
            <p className="community-post-body">{view.body}</p>
          </>
        )}
        <div className="community-post-actions">
          <button type="button" className="ghost community-touch-btn" onClick={() => void toggleLike()}>
            {thread.liked_by_me ? "♥" : "♡"} {thread.like_count}
          </button>
          <button
            type="button"
            className="ghost community-touch-btn"
            onClick={() => {
              if (reportOpen) {
                setReportOpen(false);
                setReportConfirm(false);
              } else {
                setReportConfirm(true);
              }
            }}
          >
            {t("community.report")}
          </button>
          {thread.is_self && !thread.deleted && !isRules ? (
            <>
              <button
                type="button"
                className="ghost community-touch-btn"
                onClick={() => {
                  setEditTitle(thread.title);
                  setEditBody(thread.body || "");
                  setEditOpen(true);
                }}
              >
                {t("community.edit")}
              </button>
              <button type="button" className="ghost community-touch-btn" onClick={() => setDeleteConfirm(true)}>
                {t("community.delete")}
              </button>
            </>
          ) : null}
          {isAdmin ? (
            <>
              <button type="button" className="ghost community-touch-btn" onClick={() => void adminPatch({ pinned: !thread.pinned })}>
                {thread.pinned ? t("community.unpin") : t("community.pin")}
              </button>
              <button type="button" className="ghost community-touch-btn" onClick={() => void adminPatch({ locked: !thread.locked })}>
                {thread.locked ? t("community.unlock") : t("community.lock")}
              </button>
              <button type="button" className="ghost community-touch-btn" onClick={() => void adminPatch({ deleted: !thread.deleted })}>
                {thread.deleted ? t("community.restore") : t("community.delete")}
              </button>
            </>
          ) : null}
        </div>
        {actionError ? <p className="error-text">{actionError}</p> : null}
        <ConfirmDialog
          open={reportConfirm}
          title={t("community.confirm_title")}
          message={t("community.report_confirm")}
          confirmLabel={t("community.confirm_ok")}
          cancelLabel={t("community.confirm_cancel")}
          onConfirm={() => {
            setReportConfirm(false);
            setReportOpen(true);
          }}
          onCancel={() => setReportConfirm(false)}
        />
        <ConfirmDialog
          open={deleteConfirm}
          title={t("community.confirm_title")}
          message={t("community.delete_confirm")}
          confirmLabel={t("community.confirm_ok")}
          cancelLabel={t("community.confirm_cancel")}
          danger
          onConfirm={() => void confirmDeleteThread()}
          onCancel={() => setDeleteConfirm(false)}
        />
        {reportOpen ? (
          <ReportBox targetType="thread" targetId={thread.id} onDone={() => setReportOpen(false)} />
        ) : null}
      </article>

      <h2>{t("community.discussion")}</h2>
      <div className="community-posts">
        {posts.map((p) => (
          <PostNode
            key={p.id}
            post={p}
            threadId={threadId}
            locked={thread.locked}
            onRefresh={() => void reload()}
            onLikeUpdate={patchPostLike}
          />
        ))}
        {!posts.length ? <p className="muted">{t("community.no_replies")}</p> : null}
      </div>

      {!thread.locked ? (
        isLoggedIn ? (
          <form className="community-form" onSubmit={(e) => void submitReply(e)}>
            <h3>{t("community.write_reply")}</h3>
            <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={5} maxLength={BODY_MAX} required />
            <label className="community-check">
              <input type="checkbox" checked={anonymous} onChange={(e) => setAnonymous(e.target.checked)} />
              {t("community.post_anonymous")}
            </label>
            <button type="submit" disabled={busy || !body.trim()}>
              {t("community.submit_reply")}
            </button>
          </form>
        ) : (
          <button type="button" onClick={() => requestLogin()}>
            {t("community.login_to_reply")}
          </button>
        )
      ) : (
        <p className="muted">{t("community.thread_locked_note")}</p>
      )}
    </div>
  );
}
