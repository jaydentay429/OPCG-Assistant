"use client";

import { fetchSharedBinder, prefetchCardImages } from "@/lib/api";
import { displayCardId } from "@/lib/cardId";
import { useI18n } from "@/lib/i18n";
import type { BinderSharedResponse } from "@/lib/types";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { CardImg } from "./CardImg";

export function BinderSharedClient({ token }: { token: string }) {
  const { t } = useI18n();
  const [data, setData] = useState<BinderSharedResponse | null>(null);
  const [error, setError] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    fetchSharedBinder(token)
      .then((res) => {
        if (!cancelled) {
          setData(res);
          const ids: string[] = [];
          for (const pageSlots of res.pages || []) {
            for (const cid of pageSlots || []) {
              if (cid) ids.push(cid);
            }
          }
          prefetchCardImages(ids);
        }
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const slots = useMemo(() => {
    const row = data?.pages?.[page - 1];
    return Array.isArray(row) ? row : Array.from({ length: 18 }, () => null);
  }, [data, page]);

  const title = (data?.page_titles?.[page - 1] || "").trim();
  const filled = slots.filter(Boolean).length;

  function renderSheet(start: number) {
    const sheet = slots.slice(start, start + 9);
    return (
      <div className="binder-sheet">
        <div className="binder-grid">
          {sheet.map((cid, i) => {
            const idx = start + i;
            return (
              <div key={idx} className={`binder-slot ${cid ? "filled" : "empty"}`} title={cid ? displayCardId(cid) : ""}>
                {cid ? (
                  <div className="binder-card">
                    <CardImg cardId={cid} alt="" className="binder-pocket-img" loading="lazy" />
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  if (loading) return <p className="muted">…</p>;
  if (error || !data) {
    return (
      <div className="stack">
        <h1 className="page-title">{t("binder.share_view_title")}</h1>
        <p style={{ color: "#fca5a5" }}>{error || t("binder.share_not_found")}</p>
        <Link href="/binder">{t("binder.share_back")}</Link>
      </div>
    );
  }

  return (
    <div className="stack">
      <h1 className="page-title">{t("binder.share_view_title")}</h1>
      <p className="muted">
        {data.owner_name
          ? t("binder.share_by", { name: data.owner_name })
          : t("binder.share_readonly")}
      </p>
      <div className="binder-workspace">
        <section className="deck-panel binder-panel binder-main">
          <div className="collector-stats-grid binder-stats">
            <div className="collector-stat-card">
              <span className="muted">{t("binder.page_label")}</span>
              <strong>
                {page} / 10
              </strong>
            </div>
            <div className="collector-stat-card">
              <span className="muted">{t("binder.filled_slots")}</span>
              <strong>
                {filled} / 18
              </strong>
            </div>
            {title ? (
              <div className="collector-stat-card full">
                <strong>{title}</strong>
              </div>
            ) : null}
          </div>

          <h2 className="deck-section-title">{t("binder.wall_heading", { page })}</h2>
          <div className="binder-spread">
            {renderSheet(0)}
            {renderSheet(9)}
          </div>
          <div className="binder-pagination">
            <div className="binder-pagination-nav">
              <button type="button" className="secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                ‹
              </button>
              <select value={page} onChange={(e) => setPage(Number(e.target.value))}>
                {Array.from({ length: 10 }, (_, i) => i + 1).map((p) => (
                  <option key={p} value={p}>
                    {p} / 10
                  </option>
                ))}
              </select>
              <button type="button" className="secondary" disabled={page >= 10} onClick={() => setPage((p) => p + 1)}>
                ›
              </button>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
