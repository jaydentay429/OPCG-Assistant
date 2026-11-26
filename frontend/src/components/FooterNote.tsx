"use client";

import Link from "next/link";
import { useI18n } from "@/lib/i18n";
import { useLocalizedHref } from "@/lib/langNav";

export function FooterNote() {
  const { t } = useI18n();
  const href = useLocalizedHref();
  return (
    <footer className="site-footer">
      <nav className="footer-sitemap" aria-label={t("nav.main")}>
        <Link href={href("/search")}>{t("nav.search")}</Link>
        <Link href={href("/builder")}>{t("nav.builder")}</Link>
        <Link href={href("/tournaments")}>{t("nav.tournaments")}</Link>
        <Link href={href("/leaders")}>{t("nav.leaders")}</Link>
        <Link href={href("/prices")}>{t("nav.prices")}</Link>
        <Link href={href("/play")}>{t("nav.play")}</Link>
        <Link href={href("/sets")}>{t("nav.sets")}</Link>
        <Link href={href("/collector")}>{t("nav.collector")}</Link>
        <Link href={href("/binder")}>{t("nav.binder")}</Link>
        <Link href={href("/community")}>{t("nav.community")}</Link>
        <Link href={href("/photo")}>{t("search.photo_btn")}</Link>
      </nav>
      <p className="footer-note">
        <span>optcgassistant.com</span>
        <span aria-hidden="true"> · </span>
        <Link href={href("/legal/disclaimer")} className="footer-unofficial">
          {t("footer.unofficial")}
        </Link>
        <span aria-hidden="true"> · </span>
        <a href="mailto:jaydentay429@gmail.com" title={t("sponsor.desc")}>
          {t("sponsor.title")}
        </a>
        <span aria-hidden="true"> · </span>
        <span>{t("footer.disclaimer")}</span>
        <span aria-hidden="true"> · </span>
        <Link href={href("/legal/terms")}>{t("legal.terms.title")}</Link>
        <span aria-hidden="true"> · </span>
        <Link href={href("/legal/privacy")}>{t("legal.privacy.title")}</Link>
      </p>
    </footer>
  );
}
