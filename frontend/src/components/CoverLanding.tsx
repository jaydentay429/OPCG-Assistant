"use client";

import Link from "next/link";
import { useEffect } from "react";
import { useI18n } from "@/lib/i18n";
import { markTabNavScrollReset } from "@/lib/scrollRestore";

export function CoverLanding() {
  const { t } = useI18n();

  useEffect(() => {
    document.body.classList.add("cover-active");
    return () => {
      document.body.classList.remove("cover-active");
    };
  }, []);

  return (
    <section className="cover" aria-label={t("cover.aria")}>
      <div className="cover-bg" aria-hidden="true">
        <div className="cover-bg-wash" />
        <div className="cover-bg-table" />
        <div className="cover-bg-beam" />
        <div className="cover-bg-dots" />
        <div className="cover-bg-vignette" />
      </div>

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
        </div>
      </div>
    </section>
  );
}
