"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { CardImg } from "@/components/CardImg";
import { fetchBattleReplays, type BattleReplaySummary } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";

function formatWhen(ts: number, lang: string): string {
  try {
    return new Intl.DateTimeFormat(lang, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(ts * 1000));
  } catch {
    return new Date(ts * 1000).toLocaleString();
  }
}

function modeLabel(mode: string, t: (k: string) => string): string {
  if (mode === "ai") return t("play.history_mode_ai");
  if (mode === "hotseat") return t("play.history_mode_hotseat");
  return t("play.history_mode_pvp");
}

export function BattleHistoryClient() {
  const { t, lang } = useI18n();
  const { token, isLoggedIn, ready } = useAuth();
  const [rows, setRows] = useState<BattleReplaySummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const list = await fetchBattleReplays(token);
      setRows(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    if (!ready) return;
    if (!isLoggedIn || !token) {
      setLoading(false);
      return;
    }
    void load();
  }, [ready, isLoggedIn, token, load]);

  if (!ready) return <p className="muted">…</p>;

  if (!isLoggedIn) {
    return (
      <section className="play-lobby">
        <h1 className="page-title">{t("play.history_title")}</h1>
        <p className="muted">{t("play.history_login")}</p>
        <div className="play-actions">
          <Link href="/play" className="secondary">
            {t("play.back")}
          </Link>
        </div>
      </section>
    );
  }

  return (
    <section className="play-lobby play-history">
      <h1 className="page-title">{t("play.history_title")}</h1>
      <p className="muted">{t("play.history_subtitle")}</p>
      <div className="play-actions">
        <Link href="/play" className="play-back-link-btn">
          {t("play.back")}
        </Link>
      </div>
      {loading ? <p className="muted">{t("play.history_loading")}</p> : null}
      {error ? <p className="error-text">{error}</p> : null}
      {!loading && !error && rows.length === 0 ? <p className="muted">{t("play.history_empty")}</p> : null}
      <ul className="play-history-list">
        {rows.map((row) => {
          const winnerName =
            row.winner_seat === 0 ? row.p0_username : row.winner_seat === 1 ? row.p1_username : "—";
          return (
            <li key={row.id} className="play-history-item">
              <Link href={`/play/history/${encodeURIComponent(row.id)}`} className="play-history-link">
                <div className="play-history-leaders">
                  <CardImg cardId={row.p0_leader} className="play-history-leader-img" loading="lazy" />
                  <span className="play-history-vs">vs</span>
                  <CardImg cardId={row.p1_leader} className="play-history-leader-img" loading="lazy" />
                </div>
                <div className="play-history-meta">
                  <strong>
                    {row.p0_username} vs {row.p1_username}
                  </strong>
                  <span className="muted">
                    {modeLabel(row.mode, t)} · {formatWhen(row.created_at, lang)} · {t("play.history_turns", { n: row.turn_number })}
                  </span>
                  <span className="muted">
                    {t("play.history_winner", { name: winnerName })} · {t("play.history_frames", { n: row.frame_count })}
                  </span>
                </div>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
