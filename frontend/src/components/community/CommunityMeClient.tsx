"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { fetchCommunityMyPosts, fetchCommunityMyThreads } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatRelativeTime } from "@/lib/formatRelativeTime";
import { useI18n } from "@/lib/i18n";
import type { CommunityPost, CommunityThread } from "@/lib/types";
import { catTitle, displayName } from "./communityUtils";
import { localizeCommunityRulesThread } from "./communityRulesI18n";

const PAGE_SIZE = 30;

function ListSkeleton() {
  return (
    <ul className="community-thread-list">
      {Array.from({ length: 4 }).map((_, i) => (
        <li key={i} className="community-skeleton community-skeleton-card" />
      ))}
    </ul>
  );
}

export function CommunityMeClient() {
  const { t, lang } = useI18n();
  const { token, isLoggedIn, ready, requestLogin } = useAuth();
  const [tab, setTab] = useState<"threads" | "posts">("threads");
  const [threads, setThreads] = useState<CommunityThread[]>([]);
  const [posts, setPosts] = useState<CommunityPost[]>([]);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    (nextOffset: number, append: boolean) => {
      if (!token) return Promise.resolve();
      if (append) setLoadingMore(true);
      else setLoading(true);
      setError(null);
      const req =
        tab === "threads"
          ? fetchCommunityMyThreads(token, { limit: PAGE_SIZE, offset: nextOffset })
          : fetchCommunityMyPosts(token, { limit: PAGE_SIZE, offset: nextOffset });
      return req
        .then((res) => {
          if (tab === "threads") {
            const r = res as Awaited<ReturnType<typeof fetchCommunityMyThreads>>;
            setThreads((prev) => (append ? [...prev, ...r.threads] : r.threads));
            setTotal(r.total);
            setHasMore(r.has_more);
          } else {
            const r = res as Awaited<ReturnType<typeof fetchCommunityMyPosts>>;
            setPosts((prev) => (append ? [...prev, ...r.posts] : r.posts));
            setTotal(r.total);
            setHasMore(r.has_more);
          }
          setOffset(nextOffset);
        })
        .catch((e) => setError(e instanceof Error ? e.message : String(e)))
        .finally(() => {
          setLoading(false);
          setLoadingMore(false);
        });
    },
    [token, tab],
  );

  useEffect(() => {
    if (ready && token) void load(0, false);
  }, [ready, token, load]);

  if (!ready) return <p className="muted">{t("community.loading")}</p>;
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

  return (
    <div className="community-page">
      <p className="community-back-row">
        <Link href="/community" className="community-nav-btn">
          {t("community.back")}
        </Link>
      </p>
      <h1>{t("community.my_posts")}</h1>
      <div className="community-chips community-me-tabs">
        <button type="button" className={tab === "threads" ? "is-active" : "secondary"} onClick={() => setTab("threads")}>
          {t("community.my_threads_tab")}
        </button>
        <button type="button" className={tab === "posts" ? "is-active" : "secondary"} onClick={() => setTab("posts")}>
          {t("community.my_replies")}
        </button>
      </div>

      {error ? <p className="error-text">{error}</p> : null}
      {loading ? <ListSkeleton /> : null}
      {!loading && total > 0 ? <p className="muted">{t("community.total_n", { n: total })}</p> : null}

      {tab === "threads" && !loading ? (
        <ul className="community-thread-list">
          {threads.map((raw) => {
            const th = localizeCommunityRulesThread(raw, lang);
            return (
            <li key={th.id} className={th.pinned ? "is-pinned" : ""}>
              <Link href={`/community/${th.id}`}>
                <div className="community-thread-meta">
                  {th.category_slug ? <span className="community-cat-label">{catTitle(th, lang)}</span> : null}
                  {th.anonymous ? <span className="community-badge">{t("community.anonymous")}</span> : null}
                  <span className="muted">{formatRelativeTime(th.updated_at, lang, t)}</span>
                </div>
                <strong className="community-thread-title">{th.title}</strong>
                {th.excerpt ? <p className="community-thread-excerpt muted">{th.excerpt}</p> : null}
              </Link>
            </li>
            );
          })}
        </ul>
      ) : null}

      {tab === "posts" && !loading ? (
        <ul className="community-thread-list">
          {posts.map((p) => (
            <li key={p.id}>
              <Link href={`/community/${p.thread_id}#post-${p.id}`}>
                <div className="community-thread-meta muted">
                  {p.thread_title ? <span>{p.thread_title}</span> : null}
                  <span>· {formatRelativeTime(p.created_at, lang, t)}</span>
                </div>
                <p className="community-thread-excerpt">{p.body}</p>
                <span className="muted">{displayName(p, t)}</span>
              </Link>
            </li>
          ))}
        </ul>
      ) : null}

      {!loading && !threads.length && tab === "threads" ? <p className="muted">{t("community.empty")}</p> : null}
      {!loading && !posts.length && tab === "posts" ? <p className="muted">{t("community.no_replies")}</p> : null}

      {hasMore ? (
        <div className="community-load-more">
          <button type="button" className="secondary" disabled={loadingMore} onClick={() => void load(offset + PAGE_SIZE, true)}>
            {loadingMore ? t("community.loading") : t("community.load_more")}
          </button>
        </div>
      ) : null}
    </div>
  );
}
