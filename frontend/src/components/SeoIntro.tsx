"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchTopdecksMeta } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { formatMetaLabel, latestTournamentMetaKeys, tournamentSetsFallback } from "@/lib/tournamentMeta";

/** Brand + feature copy for crawlers; visually hidden (meta/JSON-LD already cover SEO). */
export function HomeSeoIntro() {
  const { t, lang } = useI18n();
  const [sets, setSets] = useState(tournamentSetsFallback(lang));
  useEffect(() => {
    let cancelled = false;
    fetchTopdecksMeta()
      .then((res) => {
        if (cancelled) return;
        setSets(formatMetaLabel(latestTournamentMetaKeys(res.formats)) || tournamentSetsFallback(lang));
      })
      .catch(() => {
        if (!cancelled) setSets(tournamentSetsFallback(lang));
      });
    return () => {
      cancelled = true;
    };
  }, [lang]);
  return (
    <section className="home-seo-intro seo-only" aria-hidden="true">
      <h2>{t("landing.brand_heading")}</h2>
      <p>{t("landing.brand_aliases")}</p>
      <p>{t("landing.intro", { sets })}</p>
      <p>
        <Link href="/search">{t("nav.search")}</Link>
        {" · "}
        <Link href="/builder">{t("nav.builder")}</Link>
        {" · "}
        <Link href="/tournaments">{t("nav.tournaments")}</Link>
        {" · "}
        <Link href="/play">{t("nav.play")}</Link>
        {" · "}
        <Link href="/sets">{t("nav.sets")}</Link>
        {" · "}
        <Link href="/prices">{t("nav.prices")}</Link>
      </p>
    </section>
  );
}

export function PlaySeoIntro() {
  const { t } = useI18n();
  return (
    <section className="play-seo-intro seo-only" aria-hidden="true">
      <h2 className="play-seo-title">{t("play.seo_title")}</h2>
      <p>{t("play.seo_intro")}</p>
    </section>
  );
}

export function CommunitySeoIntro() {
  const { t } = useI18n();
  return (
    <p className="community-seo-intro seo-only" aria-hidden="true">
      {t("community.seo_intro")}
    </p>
  );
}

export function PhotoSeoIntro() {
  const { t } = useI18n();
  return (
    <p className="photo-seo-intro seo-only" aria-hidden="true">
      {t("photo.seo_intro")}
    </p>
  );
}
