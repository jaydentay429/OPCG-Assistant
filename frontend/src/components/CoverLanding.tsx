"use client";

import Link from "next/link";
import { useEffect } from "react";
import { CardImg } from "@/components/CardImg";
import { CoverUpdates } from "@/components/CoverUpdates";
import { useI18n } from "@/lib/i18n";
import { homeDocumentTitle, usePinnedDocumentTitle } from "@/lib/pinnedDocumentTitle";
import { markTabNavScrollReset } from "@/lib/scrollRestore";

/** Real cards shown beside the cover copy; each links to its card page. */
const COVER_CARDS = ["OP01-120", "OP05-119", "OP01-001"] as const;

export function CoverLanding() {
  const { lang, t } = useI18n();
  usePinnedDocumentTitle(homeDocumentTitle(lang));

  useEffect(() => {
    document.body.classList.add("cover-active");
    return () => {
      document.body.classList.remove("cover-active");
    };
  }, []);

  return (
    <section className="cover" aria-label={t("cover.aria")}>
      <div className="cover-stage">
        <div className="cover-content">
          <p className="cover-kicker">{t("cover.kicker")}</p>
          <h1 className="cover-brand">{t("app.page_title")}</h1>
          <p className="cover-host">optcgassistant.com · OPCG Assistant</p>
          <p className="cover-tagline">{t("cover.tagline")}</p>
          <div className="cover-ctas">
            <Link
              href="/search"
              className="cover-cta cover-cta-primary"
              onClick={() => markTabNavScrollReset()}
            >
              {t("cover.cta_search")}
            </Link>
            <Link
              href="/builder"
              className="cover-cta cover-cta-secondary"
              onClick={() => markTabNavScrollReset()}
            >
              {t("cover.cta_builder")}
            </Link>
            <Link
              href="/play"
              className="cover-cta cover-cta-secondary"
              onClick={() => markTabNavScrollReset()}
            >
              {t("cover.cta_play")}
            </Link>
            <Link
              href="/community"
              className="cover-cta cover-cta-secondary"
              onClick={() => markTabNavScrollReset()}
            >
              {t("cover.cta_community")}
            </Link>
          </div>
          <p className="cover-unofficial">
            <Link href="/legal/disclaimer">{t("cover.unofficial")}</Link>
          </p>
          <CoverUpdates />
        </div>
        <div className="cover-fan">
          {COVER_CARDS.map((id) => (
            <Link key={id} href={`/cards/${id}`} className="cover-fan-card">
              <CardImg cardId={id} alt={id} loading="eager" />
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}
