"use client";

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import { fetchAiBattleDecks } from "@/lib/api";
import { probeBattleService, type BattleServiceStatus } from "@/lib/battleAvailability";
import { useI18n } from "@/lib/i18n";

export function BattleUnavailableNotice({ onRetry }: { onRetry?: () => void }) {
  const { t } = useI18n();
  return (
    <section className="play-unavailable" aria-labelledby="play-unavailable-title">
      <h1 id="play-unavailable-title" className="page-title">
        {t("play.unavailable_title")}
      </h1>
      <p>{t("play.unavailable_body")}</p>
      <div className="play-unavailable-actions">
        {onRetry ? (
          <button type="button" onClick={onRetry}>
            {t("play.unavailable_retry")}
          </button>
        ) : null}
        <Link href="/builder">{t("play.unavailable_builder")}</Link>
        <Link href="/search" className="secondary">
          {t("play.unavailable_search")}
        </Link>
      </div>
    </section>
  );
}

/**
 * One availability check. While BATTLE_ENABLED is off, /battle/ai-decks is 404
 * and this notice replaces the lobby so polls and sockets never start.
 */
export function BattleAvailabilityGate({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<BattleServiceStatus>("loading");
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    probeBattleService(() => fetchAiBattleDecks()).then((next) => {
      if (!cancelled) setStatus(next === "ready" ? "ready" : "unavailable");
    });
    return () => {
      cancelled = true;
    };
  }, [nonce]);

  if (status === "loading") {
    return (
      <section className="play-unavailable" aria-busy="true">
        <p className="muted">…</p>
      </section>
    );
  }
  if (status === "unavailable") {
    return <BattleUnavailableNotice onRetry={() => setNonce((value) => value + 1)} />;
  }
  return children;
}
