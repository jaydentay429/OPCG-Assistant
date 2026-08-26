"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  createCardComment,
  deleteCardComment,
  fetchCardComments,
  fetchCardTournaments,
  likeCardComment,
  reportCardComment,
  type CardComment,
  type CardTournamentAppearance,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { localizeCardName } from "@/lib/cardLocale";
import { displayCardId } from "@/lib/cardId";
import { useI18n } from "@/lib/i18n";
import { flushCurrentScroll } from "@/lib/scrollRestore";
import { displayAuthor, displayKeepingParens, pickFacetLabel } from "@/lib/topdeckLocale";
import { CardImg } from "./CardImg";
import { ConfirmDialog } from "./community/ConfirmDialog";

function formatCommentTime(raw: string, lang: string): string {
  const d = new Date(raw);
  if (!Number.isFinite(d.getTime())) return raw || "";
  const locale = lang === "en" ? "en-US" : lang === "zh-Hant" ? "zh-HK" : "zh-CN";
  return new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(d);
}

export function CardDetailExtras({
  cardId,
  sections = "all",
}: {
  cardId: string;
  /** all = tournaments + comments; or only one block for layout placement */
  sections?: "all" | "tournaments" | "comments";
}) {
  const { t, lang } = useI18n();
  const { token, isLoggedIn, requestLogin } = useAuth();
  const showTournaments = sections === "all" || sections === "tournaments";
  const showComments = sections === "all" || sections === "comments";
  const [tourneys, setTourneys] = useState<CardTournamentAppearance[]>([]);
  const [tourneyTotal, setTourneyTotal] = useState(0);
  const [tourneyLoading, setTourneyLoading] = useState(true);
  const [comments, setComments] = useState<CardComment[]>([]);
  const [commentTotal, setCommentTotal] = useState(0);
  const [commentLoading, setCommentLoading] = useState(true);
  const [draft, setDraft] = useState("");
  const [anonymous, setAnonymous] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reportId, setReportId] = useState<number | null>(null);
  const [reportReason, setReportReason] = useState("");
  const [reportConfirmId, setReportConfirmId] = useState<number | null>(null);

  const loadComments = useCallback(async () => {
    if (!showComments) return;
    setCommentLoading(true);
    setError("");
    try {
      const res = await fetchCardComments(cardId, { token, limit: 50 });
      setComments(res.comments || []);
      setCommentTotal(res.total || 0);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setComments([]);
      setCommentTotal(0);
    } finally {
      setCommentLoading(false);
    }
  }, [cardId, token, showComments]);

  useEffect(() => {
    if (!showComments) return;
    setDraft("");
    setAnonymous(false);
    setReportId(null);
    setReportReason("");
    setReportConfirmId(null);
    void loadComments();
  }, [cardId, showComments, loadComments]);
  useEffect(() => {
    if (!showTournaments) return;
    let cancelled = false;
    setTourneyLoading(true);
    fetchCardTournaments(cardId, 10)
      .then((res) => {
        if (cancelled) return;
        setTourneys(res.items || []);
        setTourneyTotal(res.total_matched || 0);
      })
      .catch(() => {
        if (cancelled) return;
        setTourneys([]);
        setTourneyTotal(0);
      })
      .finally(() => {
        if (!cancelled) setTourneyLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [cardId, showTournaments]);

  async function submitComment() {
    if (!token) {
      requestLogin();
      return;
    }
    const body = draft.trim();
    if (body.length < 2) {
      setError(t("detail.comment_too_short"));
      return;
    }
    setBusy(true);
    setError("");
    try {
      const created = await createCardComment(token, cardId, { body, anonymous });
      setComments((prev) => [created, ...prev]);
      setCommentTotal((n) => n + 1);
      setDraft("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function toggleLike(c: CardComment) {
    if (!token) {
      requestLogin();
      return;
    }
    const prevLiked = c.liked_by_me;
    const prevCount = c.like_count;
    const nextLiked = !prevLiked;
    setComments((list) =>
      list.map((x) =>
        x.id === c.id
          ? { ...x, liked_by_me: nextLiked, like_count: Math.max(0, prevCount + (nextLiked ? 1 : -1)) }
          : x,
      ),
    );
    try {
      const res = await likeCardComment(token, c.id, nextLiked);
      setComments((list) =>
        list.map((x) =>
          x.id === c.id ? { ...x, liked_by_me: res.liked_by_me, like_count: res.like_count } : x,
        ),
      );
    } catch {
      setComments((list) =>
        list.map((x) => (x.id === c.id ? { ...x, liked_by_me: prevLiked, like_count: prevCount } : x)),
      );
    }
  }

  async function submitReport() {
    if (reportId == null || !token) return;
    setBusy(true);
    setError("");
    try {
      await reportCardComment(token, reportId, reportReason.trim());
      setReportId(null);
      setReportReason("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function removeComment(id: number) {
    if (!token) return;
    setBusy(true);
    try {
      await deleteCardComment(token, id);
      setComments((list) => list.filter((x) => x.id !== id));
      setCommentTotal((n) => Math.max(0, n - 1));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={`card-detail-extras${sections === "comments" ? " is-under-thumbs" : ""}`}>
      {showTournaments ? (
      <section className="card-detail-section">
        <div className="card-detail-section-head">
          <h3>{t("detail.tournaments_title")}</h3>
          <p className="muted">
            {tourneyLoading
              ? t("detail.tournaments_loading")
              : t("detail.tournaments_hint", { n: tourneyTotal, shown: Math.min(10, tourneys.length) })}
          </p>
        </div>
        {!tourneyLoading && tourneys.length === 0 ? (
          <p className="muted">{t("detail.tournaments_empty")}</p>
        ) : (
          <div className="card-tourney-list">
            {tourneys.map((row) => {
              const leaderName =
                localizeCardName(row.leader_name, row.leader_name_en, lang) ||
                row.leader_name ||
                row.leader ||
                "—";
              const metaLine = [
                row.date,
                displayKeepingParens(lang, row.placement, row.placement_key, row.placement_labels),
                displayKeepingParens(lang, row.tournament, row.tournament_key, row.tournament_labels),
                pickFacetLabel(lang, row.country_key || row.country || "", row.country_labels),
                row.host,
                displayAuthor(row.author, t("tournaments.player_unknown")),
              ]
                .map((x) => String(x || "").trim())
                .filter(Boolean)
                .join(" · ");
              return (
                <Link
                  key={row.id}
                  href={`/tournaments?deck=${encodeURIComponent(row.id)}&return=${encodeURIComponent(`/cards/${encodeURIComponent(cardId)}`)}`}
                  className="card-tourney-row"
                  scroll={false}
                  onPointerDown={() => flushCurrentScroll()}
                  onClick={() => {
                    flushCurrentScroll();
                    try {
                      sessionStorage.setItem(
                        "opcg_tourney_return",
                        `/cards/${encodeURIComponent(cardId)}`,
                      );
                    } catch {
                      /* ignore */
                    }
                  }}
                >
                  <span className="card-tourney-art">
                    {row.leader ? <CardImg cardId={row.leader} alt={leaderName} /> : null}
                  </span>
                  <span className="card-tourney-main">
                    <strong>{leaderName}</strong>
                    <span className="muted">{metaLine}</span>
                  </span>
                  <span className="card-tourney-qty">
                    {row.is_leader ? t("detail.tournaments_as_leader") : `×${row.qty || 1}`}
                  </span>
                </Link>
              );
            })}
          </div>
        )}
        {tourneyTotal > 10 ? (
          <p className="muted card-detail-more">
            <Link href={`/tournaments?q=${encodeURIComponent(displayCardId(cardId))}`}>
              {t("detail.tournaments_more")}
            </Link>
          </p>
        ) : null}
      </section>
      ) : null}

      {showComments ? (
      <section className="card-detail-section card-detail-comments">
        <div className="card-detail-section-head">
          <h3>{t("detail.comments_title")}</h3>
          <p className="muted">{t("detail.comments_count", { n: commentTotal })}</p>
        </div>

        <div className="card-comment-compose">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={3}
            maxLength={2000}
            placeholder={isLoggedIn ? t("detail.comment_placeholder") : t("detail.comment_need_login")}
            disabled={busy || !isLoggedIn}
            onFocus={() => {
              if (!isLoggedIn) requestLogin();
            }}
          />
          <div className="card-comment-compose-actions">
            <label className="card-comment-anon">
              <input
                type="checkbox"
                checked={anonymous}
                disabled={!isLoggedIn || busy}
                onChange={(e) => setAnonymous(e.target.checked)}
              />
              {t("detail.comment_anonymous")}
            </label>
            <button type="button" disabled={busy || !isLoggedIn || !draft.trim()} onClick={() => void submitComment()}>
              {t("detail.comment_submit")}
            </button>
          </div>
        </div>

        {error ? <p className="error-text">{error}</p> : null}
        {commentLoading ? <p className="muted">{t("detail.comments_loading")}</p> : null}
        {!commentLoading && comments.length === 0 ? <p className="muted">{t("detail.comments_empty")}</p> : null}

        <ul className="card-comment-list">
          {comments.map((c) => (
            <li key={c.id} className="card-comment-item">
              <div className="card-comment-meta">
                <strong>{c.anonymous || !c.author_username ? t("detail.comment_anon_name") : c.author_username}</strong>
                <span className="muted">{formatCommentTime(c.created_at, lang)}</span>
              </div>
              <p className="card-comment-body">{c.body}</p>
              <div className="card-comment-actions">
                <button
                  type="button"
                  className={`ghost card-comment-like${c.liked_by_me ? " is-liked" : ""}`}
                  onClick={() => void toggleLike(c)}
                >
                  {c.liked_by_me ? "♥" : "♡"} {c.like_count}
                </button>
                <button
                  type="button"
                  className="ghost"
                  onClick={() => {
                    if (!isLoggedIn) {
                      requestLogin();
                      return;
                    }
                    setReportConfirmId(c.id);
                  }}
                >
                  {t("detail.comment_report")}
                </button>
                {c.is_self ? (
                  <button type="button" className="ghost" onClick={() => void removeComment(c.id)}>
                    {t("detail.comment_delete")}
                  </button>
                ) : null}
              </div>
              {reportId === c.id ? (
                <div className="card-comment-report">
                  <textarea
                    value={reportReason}
                    onChange={(e) => setReportReason(e.target.value)}
                    rows={3}
                    maxLength={500}
                    placeholder={t("detail.comment_report_ph")}
                  />
                  <div className="card-comment-compose-actions">
                    <button type="button" className="secondary" onClick={() => setReportId(null)}>
                      {t("detail.comment_cancel")}
                    </button>
                    <button
                      type="button"
                      disabled={busy || reportReason.trim().length < 5}
                      onClick={() => void submitReport()}
                    >
                      {t("detail.comment_report_submit")}
                    </button>
                  </div>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      </section>
      ) : null}

      {showComments ? (
      <ConfirmDialog
        open={reportConfirmId != null}
        title={t("detail.comment_report")}
        message={t("detail.comment_report_confirm")}
        confirmLabel={t("detail.comment_confirm_ok")}
        cancelLabel={t("detail.comment_cancel")}
        onConfirm={() => {
          setReportId(reportConfirmId);
          setReportConfirmId(null);
          setReportReason("");
        }}
        onCancel={() => setReportConfirmId(null)}
      />
      ) : null}
    </div>
  );
}
