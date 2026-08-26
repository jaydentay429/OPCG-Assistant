"use client";

import Link from "next/link";
import { useI18n } from "@/lib/i18n";

type DocId = "disclaimer" | "terms" | "privacy";

const PARA_COUNTS: Record<DocId, number> = {
  disclaimer: 6,
  terms: 5,
  privacy: 5,
};

export function LegalDoc({ doc }: { doc: DocId }) {
  const { t } = useI18n();
  const n = PARA_COUNTS[doc];
  const paragraphs = Array.from({ length: n }, (_, i) => t(`legal.${doc}.p${i + 1}`));

  return (
    <article className="legal-doc stack">
      <p className="legal-crumb">
        <Link href="/">{t("app.page_title")}</Link>
        <span aria-hidden="true"> / </span>
        <span>{t(`legal.${doc}.title`)}</span>
      </p>
      <h1 className="page-title">{t(`legal.${doc}.title`)}</h1>
      <p className="muted legal-updated">{t("legal.updated")}</p>
      {paragraphs.map((text, i) => (
        <p key={i} className="legal-para">
          {text}
        </p>
      ))}
      <p className="legal-links">
        <Link href="/legal/disclaimer">{t("legal.disclaimer.title")}</Link>
        <span aria-hidden="true"> · </span>
        <Link href="/legal/terms">{t("legal.terms.title")}</Link>
        <span aria-hidden="true"> · </span>
        <Link href="/legal/privacy">{t("legal.privacy.title")}</Link>
      </p>
    </article>
  );
}
