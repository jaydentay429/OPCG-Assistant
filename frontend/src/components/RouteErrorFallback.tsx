"use client";

import { recoverChunkErrorFromBoundary } from "@/lib/chunkReload";
import { readStoredLang, translate, useOptionalI18n, type Lang } from "@/lib/i18n";
import { useEffect, useState } from "react";

/**
 * Shared fallback for `error.tsx` and `global-error.tsx`.
 * Does not read or write the deck draft in localStorage.
 * Chunk failures may navigate or reload once; every other error only renders.
 *
 * Do not add a robots noindex meta. A chunk failure is painted on the client
 * over a normal 200 document; Googlebot can hit that and drop an indexed card
 * page. Server render failures already respond with 5xx.
 */
export function RouteErrorFallback({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const i18n = useOptionalI18n();
  const [lang, setLang] = useState<Lang>("zh-Hant");

  useEffect(() => {
    if (!i18n) setLang(readStoredLang());
  }, [i18n]);

  useEffect(() => {
    recoverChunkErrorFromBoundary(error);
  }, [error]);

  const t = i18n?.t ?? ((key: string) => translate(lang, key));

  return (
    <div className="stack route-error" role="alert">
      <h1 className="page-title">{t("error.title")}</h1>
      <p className="muted">{t("error.body")}</p>
      <div className="route-error-actions">
        <button type="button" onClick={() => window.location.reload()}>
          {t("chunk.refresh")}
        </button>
        <button type="button" className="secondary" onClick={() => reset()}>
          {t("error.retry")}
        </button>
      </div>
    </div>
  );
}
