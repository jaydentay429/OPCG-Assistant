"use client";

import Link from "next/link";
import { useI18n } from "@/lib/i18n";

export function FooterNote() {
  const { t } = useI18n();
  return (
    <footer className="site-footer">
      <nav className="footer-sitemap" aria-label={t("nav.main")}>
        <Link href="/search">{t("nav.search")}</Link>
        <Link href="/builder">{t("nav.builder")}</Link>
        <Link href="/tournaments">{t("nav.tournaments")}</Link>
        <Link href="/prices">{t("nav.prices")}</Link>
        <Link href="/play">{t("nav.play")}</Link>
        <Link href="/sets">{t("nav.sets")}</Link>
        <Link href="/collector">{t("nav.collector")}</Link>
        <Link href="/binder">{t("nav.binder")}</Link>
        <Link href="/community">{t("nav.community")}</Link>
        <Link href="/photo">{t("search.photo_btn")}</Link>
      </nav>
      <p className="footer-note">
        <span>optcgassistant.com</span>
        <span aria-hidden="true"> · </span>
        <Link href="/legal/disclaimer" className="footer-unofficial">
          {t("footer.unofficial")}
        </Link>
        <span aria-hidden="true"> · </span>
        <a href="mailto:jaydentay429@gmail.com">{t("sponsor.title")}</a>
        <span aria-hidden="true"> · </span>
        <span>{t("footer.disclaimer")}</span>
        <span aria-hidden="true"> · </span>
        <Link href="/legal/terms">{t("legal.terms.title")}</Link>
        <span aria-hidden="true"> · </span>
        <Link href="/legal/privacy">{t("legal.privacy.title")}</Link>
      </p>
    </footer>
  );
}
