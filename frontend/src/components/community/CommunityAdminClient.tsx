"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  fetchCommunityAdminReports,
  fetchCommunityAdminThreads,
  fetchCommunityCategories,
  patchCommunityCategory,
  patchCommunityReport,
  patchCommunityAdminThread,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n, type Lang } from "@/lib/i18n";
import type { CommunityCategory, CommunityReport, CommunityThread } from "@/lib/types";
import { ConfirmDialog } from "./ConfirmDialog";
import { catTitle } from "./communityUtils";

type PendingAction =
  | { kind: "report"; id: number; status: string }
  | { kind: "thread_pin"; id: number; pinned: boolean }
  | { kind: "thread_lock"; id: number; locked: boolean }
  | { kind: "thread_delete"; id: number; deleted: boolean };

function catLabel(c: CommunityCategory, lang: Lang): string {
  return catTitle(c, lang);
}

export function CommunityAdminClient() {
  const { t, lang } = useI18n();
  const { token, isLoggedIn, isAdmin, ready, requestLogin } = useAuth();
  const [reports, setReports] = useState<CommunityReport[]>([]);
  const [threads, setThreads] = useState<CommunityThread[]>([]);
  const [categories, setCategories] = useState<CommunityCategory[]>([]);
  const [reportFilter, setReportFilter] = useState<"open" | "all" | "done">("open");
  const [reportNote, setReportNote] = useState<Record<number, string>>({});
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    if (!token || !isAdmin) return;
    setError(null);
    const status = reportFilter === "open" ? "open" : "all";
    Promise.all([
      fetchCommunityAdminReports(token, status),
      fetchCommunityAdminThreads(token),
      fetchCommunityCategories({ token, admin: true }),
    ])
      .then(([r, thRes, cats]) => {
        const filtered =
          reportFilter === "done"
            ? r.filter((x) => x.status === "resolved" || x.status === "dismissed")
            : reportFilter === "open"
              ? r.filter((x) => x.status === "open")
              : r;
        setReports(filtered);
        setThreads(thRes.threads);
        setCategories(cats);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [token, isAdmin, reportFilter]);

  useEffect(() => {
    if (ready && isAdmin) reload();
  }, [ready, isAdmin, reload]);

  async function executePending() {
    if (!token || !pending) return;
    try {
      if (pending.kind === "report") {
        await patchCommunityReport(token, pending.id, {
          status: pending.status,
          note: reportNote[pending.id]?.trim() || undefined,
        });
      } else if (pending.kind === "thread_pin") {
        await patchCommunityAdminThread(token, pending.id, { pinned: pending.pinned });
      } else if (pending.kind === "thread_lock") {
        await patchCommunityAdminThread(token, pending.id, { locked: pending.locked });
      } else if (pending.kind === "thread_delete") {
        await patchCommunityAdminThread(token, pending.id, { deleted: pending.deleted });
      }
      setPending(null);
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setPending(null);
    }
  }

  function confirmMessage(): string {
    if (!pending) return "";
    if (pending.kind === "report") return t("community.confirm_title");
    if (pending.kind === "thread_delete") return t("community.admin_confirm_delete");
    if (pending.kind === "thread_pin") return t("community.admin_confirm_pin");
    if (pending.kind === "thread_lock") return t("community.admin_confirm_lock");
    return t("community.confirm_title");
  }

  if (!ready) return <p className="muted">{t("community.loading")}</p>;
  if (!isLoggedIn) {
    return (
      <div className="community-page">
        <p>{t("community.admin_need_login")}</p>
        <button type="button" onClick={() => requestLogin()}>
          {t("auth.login")}
        </button>
      </div>
    );
  }
  if (!isAdmin) {
    return (
      <div className="community-page">
        <p className="error-text">{t("community.admin_forbidden")}</p>
        <Link href="/community" className="community-nav-btn">
          {t("community.back")}
        </Link>
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
      <h1>{t("community.admin_title")}</h1>
      {error ? <p className="error-text">{error}</p> : null}

      <ConfirmDialog
        open={pending != null}
        title={t("community.confirm_title")}
        message={confirmMessage()}
        confirmLabel={t("community.confirm_ok")}
        cancelLabel={t("community.confirm_cancel")}
        danger={pending?.kind === "thread_delete"}
        onConfirm={() => void executePending()}
        onCancel={() => setPending(null)}
      />

      <section className="community-admin-section">
        <h2>{t("community.admin_reports")}</h2>
        <div className="community-chips">
          <button
            type="button"
            className={reportFilter === "all" ? "is-active" : "secondary"}
            onClick={() => setReportFilter("all")}
          >
            {t("community.admin_filter_all")}
          </button>
          <button
            type="button"
            className={reportFilter === "open" ? "is-active" : "secondary"}
            onClick={() => setReportFilter("open")}
          >
            {t("community.admin_filter_open")}
          </button>
          <button
            type="button"
            className={reportFilter === "done" ? "is-active" : "secondary"}
            onClick={() => setReportFilter("done")}
          >
            {t("community.admin_filter_done")}
          </button>
        </div>
        {!reports.length ? <p className="muted">{t("community.admin_reports_empty")}</p> : null}
        <ul className="community-admin-list">
          {reports.map((r) => (
            <li key={r.id}>
              <div>
                <strong>
                  #{r.id} {r.target_type}:{r.target_id}
                </strong>
                <p className="muted">
                  {t("community.reporter")}: {r.reporter_username || r.reporter_user_id}
                  {r.target_author_username
                    ? ` · ${t("community.target_author")}: ${r.target_author_username}`
                    : null}
                  {r.status !== "open" ? ` · ${r.status}` : ""}
                </p>
                <p className="community-post-body">{r.reason}</p>
                {r.target_preview ? <p className="muted">「{r.target_preview}」</p> : null}
                <label className="community-report-note">
                  {t("community.admin_report_note")}
                  <input
                    value={reportNote[r.id] || ""}
                    onChange={(e) => setReportNote((prev) => ({ ...prev, [r.id]: e.target.value }))}
                    maxLength={500}
                  />
                </label>
              </div>
              <div className="community-post-actions">
                {r.target_type === "thread" ? (
                  <Link href={`/community/${r.target_id}`}>{t("community.open")}</Link>
                ) : r.thread_id ? (
                  <Link href={`/community/${r.thread_id}`}>{t("community.open")}</Link>
                ) : null}
                {r.status === "open" ? (
                  <>
                    <button
                      type="button"
                      className="success community-touch-btn"
                      onClick={() => setPending({ kind: "report", id: r.id, status: "resolved" })}
                    >
                      {t("community.resolve")}
                    </button>
                    <button
                      type="button"
                      className="secondary community-touch-btn"
                      onClick={() => setPending({ kind: "report", id: r.id, status: "dismissed" })}
                    >
                      {t("community.dismiss")}
                    </button>
                  </>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section className="community-admin-section">
        <h2>{t("community.admin_threads")}</h2>
        <ul className="community-admin-list">
          {threads.map((th) => (
            <li key={th.id}>
              <div>
                <Link href={`/community/${th.id}`}>
                  <strong>
                    #{th.id} {th.title}
                  </strong>
                </Link>
                <p className="muted">
                  {th.username || th.author_display}
                  {th.anonymous ? ` (${t("community.anonymous")})` : ""}
                  {th.deleted ? ` · ${t("community.deleted")}` : ""}
                  {th.pinned ? ` · ${t("community.pinned")}` : ""}
                  {th.locked ? ` · ${t("community.locked")}` : ""}
                </p>
              </div>
              <div className="community-post-actions">
                <button
                  type="button"
                  className="ghost community-touch-btn"
                  onClick={() => setPending({ kind: "thread_pin", id: th.id, pinned: !th.pinned })}
                >
                  {th.pinned ? t("community.unpin") : t("community.pin")}
                </button>
                <button
                  type="button"
                  className="ghost community-touch-btn"
                  onClick={() => setPending({ kind: "thread_lock", id: th.id, locked: !th.locked })}
                >
                  {th.locked ? t("community.unlock") : t("community.lock")}
                </button>
                <button
                  type="button"
                  className="ghost community-touch-btn"
                  onClick={() => setPending({ kind: "thread_delete", id: th.id, deleted: !th.deleted })}
                >
                  {th.deleted ? t("community.restore") : t("community.delete")}
                </button>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section className="community-admin-section">
        <h2>{t("community.admin_categories")}</h2>
        <ul className="community-admin-list">
          {categories.map((c) => (
            <li key={c.id}>
              <strong>{catLabel(c, lang)}</strong>
              <span className="muted">{c.active ? t("community.active") : t("community.inactive")}</span>
              <button
                type="button"
                className="secondary community-touch-btn"
                onClick={() => void patchCommunityCategory(token!, c.id, !c.active).then(reload)}
              >
                {c.active ? t("community.deactivate") : t("community.activate")}
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
