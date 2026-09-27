"use client";

import Link from "next/link";
import { useI18n } from "@/lib/i18n";

export function PlayPausedNotice() {
  const { t } = useI18n();
  return (
    <section className="play-paused" aria-labelledby="play-paused-title">
      <h1 id="play-paused-title" className="page-title">
        {t("play.paused_title")}
      </h1>
      <p>{t("play.paused_body")}</p>
      <div className="play-paused-actions">
        <Link href="/builder">{t("play.paused_builder")}</Link>
        <Link href="/search" className="secondary">
          {t("play.paused_search")}
        </Link>
      </div>
    </section>
  );
}
