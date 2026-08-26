"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  fetchBattleRankElite,
  fetchBattleRankHistory,
  fetchBattleRankLeaderboard,
  fetchBattleRankMe,
  type BattleRankHistoryEntry,
  type BattleRankLeaderboardEntry,
  type BattleRankProfile,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import {
  eliteBlockClass,
  eliteTitleClass,
  RankEliteName,
  RankEliteTier,
  type EliteTitleKey,
} from "@/components/play/RankEliteBadge";

function EliteBlock({
  titleKey,
  title,
  entries,
  empty,
}: {
  titleKey: EliteTitleKey;
  title: string;
  entries: BattleRankLeaderboardEntry[];
  empty: string;
}) {
  const blockCls = eliteBlockClass(titleKey);
  return (
    <div className={`play-rank-elite-block${blockCls ? ` ${blockCls}` : ""}`}>
      <h3>{title}</h3>
      {entries.length ? (
        <ul className="play-rank-list">
          {entries.map((e) => (
            <li key={e.user_id}>
              <RankEliteName
                name={e.username || e.user_id}
                eliteTitle={titleKey}
                eliteLabel={e.elite_title_zh || title}
                size="md"
              />
              <span className="muted rank-elite-rating"> · {e.rating}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">{empty}</p>
      )}
    </div>
  );
}

export function BattleRankClient() {
  const { t } = useI18n();
  const { token, isLoggedIn, ready } = useAuth();
  const [profile, setProfile] = useState<BattleRankProfile | null>(null);
  const [board, setBoard] = useState<BattleRankLeaderboardEntry[]>([]);
  const [elite, setElite] = useState<Record<string, BattleRankLeaderboardEntry[]>>({});
  const [history, setHistory] = useState<BattleRankHistoryEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchBattleRankLeaderboard(50)
      .then(setBoard)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    fetchBattleRankElite()
      .then(setElite)
      .catch(() => setElite({}));
  }, []);

  useEffect(() => {
    if (!token) {
      setProfile(null);
      setHistory([]);
      return;
    }
    fetchBattleRankMe(token)
      .then(setProfile)
      .catch(() => setProfile(null));
    fetchBattleRankHistory(token, 15)
      .then(setHistory)
      .catch(() => setHistory([]));
  }, [token]);

  if (!ready) return <p className="muted">…</p>;

  const meEliteCls = profile?.elite_title ? eliteTitleClass(profile.elite_title) : null;

  return (
    <section className="play-lobby play-rank-page">
      <div className="play-lobby-head">
        <div className="play-lobby-titles">
          <h1 className="page-title">{t("play.rank_page_title")}</h1>
          <p className="muted play-lobby-sub">{t("play.rank_page_sub")}</p>
        </div>
        <Link href="/play" className="play-history-link-btn">
          {t("play.rank_back_play")}
        </Link>
      </div>
      {error ? <p className="error-text">{error}</p> : null}

      {isLoggedIn && profile ? (
        <div className={`play-rank-me${meEliteCls ? ` ${meEliteCls}` : ""}`}>
          <h2>{t("play.rank_my_stats")}</h2>
          <p className="play-rank-me-line">
            <RankEliteTier label={profile.tier_label_zh} eliteTitle={profile.elite_title} />
            <span className="play-rank-me-score"> · {profile.rating}</span>
          </p>
          <p className="muted">
            {profile.wins}W / {profile.losses}L
            {profile.draws ? ` / ${profile.draws}D` : ""}
            {" · "}
            {t("play.rank_win_rate", { n: Math.round(profile.win_rate * 100) })}
            {" · "}
            {t("play.rank_peak", { n: profile.peak_rating })}
          </p>
          {profile.elite_pending ? <p className="muted">{t("play.rank_elite_pending")}</p> : null}
        </div>
      ) : (
        <p className="muted">{t("play.rank_need_login")}</p>
      )}

      <div className="play-rank-elite-grid">
        <EliteBlock
          titleKey="pirate_king"
          title={t("play.rank_elite_king")}
          entries={elite.pirate_king || []}
          empty={t("play.rank_elite_empty")}
        />
        <EliteBlock
          titleKey="emperor"
          title={t("play.rank_elite_emperor")}
          entries={elite.emperor || []}
          empty={t("play.rank_elite_empty")}
        />
        <EliteBlock
          titleKey="warlord"
          title={t("play.rank_elite_warlord")}
          entries={elite.warlord || []}
          empty={t("play.rank_elite_empty")}
        />
      </div>

      <h2>{t("play.rank_leaderboard")}</h2>
      {board.length ? (
        <ol className="play-rank-list play-rank-board">
          {board.map((e) => {
            const rowCls = eliteTitleClass(e.elite_title);
            return (
              <li key={e.user_id} className={rowCls ? `is-elite ${rowCls}` : undefined}>
                <span className="play-rank-pos">{e.rank}</span>
                <RankEliteName
                  name={e.username || e.user_id}
                  eliteTitle={e.elite_title}
                  eliteLabel={e.elite_title_zh}
                  size="sm"
                />
                <span className="muted play-rank-board-meta">
                  {" "}
                  · {e.elite_title ? e.elite_title_zh : e.tier_label_zh} · {e.rating}
                </span>
              </li>
            );
          })}
        </ol>
      ) : (
        <p className="muted">{t("play.rank_board_empty")}</p>
      )}

      {isLoggedIn && history.length ? (
        <>
          <h2>{t("play.rank_recent")}</h2>
          <ul className="play-rank-list">
            {history.map((m) => (
              <li key={`${m.room_code}-${m.created_at}`}>
                {m.result === "win" ? "+" : m.result === "loss" ? "-" : "="}
                {Math.abs(m.delta)} vs {m.opponent_username || m.opponent_user_id}
                <span className="muted">
                  {" "}
                  · {m.rating_before} → {m.rating_after}
                </span>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}
