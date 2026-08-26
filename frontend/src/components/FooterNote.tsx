"use client";

import Link from "next/link";
import { useI18n } from "@/lib/i18n";

export function FooterNote() {
  const { t } = useI18n();
  return (
    <p className="footer-note">
      <span>optcgassistant.com</span>
      <span aria-hidden="true"> · </span>
      <Link href="/legal/disclaimer" className="footer-unofficial">
        {t("footer.unofficial")}
      </Link>
      <span aria-hidden="true"> · </span>
      <span>{t("footer.disclaimer")}</span>
      <span aria-hidden="true"> · </span>
      <Link href="/legal/terms">{t("legal.terms.title")}</Link>
      <span aria-hidden="true"> · </span>
      <Link href="/legal/privacy">{t("legal.privacy.title")}</Link>
    </p>
  );
}
