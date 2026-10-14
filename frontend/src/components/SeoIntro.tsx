"use client";

import Link from "next/link";
import { useI18n } from "@/lib/i18n";

/** Brand + feature copy for crawlers; visually hidden (meta/JSON-LD already cover SEO). */
export function HomeSeoIntro() {
  const { t } = useI18n();
  return (
    <section className="home-seo-intro seo-only" aria-hidden="true">
      <h2>{t("landing.brand_heading")}</h2>
      <p>{t("landing.brand_aliases")}</p>
      <p>{t("landing.intro")}</p>
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
