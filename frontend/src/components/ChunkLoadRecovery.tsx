"use client";

import { attachChunkLoadRecovery } from "@/lib/chunkReload";
import { useI18n } from "@/lib/i18n";
import { useEffect, useState } from "react";

/**
 * Link-click chunk failures navigate once. Every other chunk failure shows
 * this fixed prompt; it stays out of document flow so the page does not jump.
 */
export function ChunkLoadRecovery() {
  const { t } = useI18n();
  const [visible, setVisible] = useState(false);

  useEffect(() => attachChunkLoadRecovery({ onPrompt: () => setVisible(true) }), []);

  return (
    <div className="chunk-update-banner" role="status" aria-live="polite" hidden={!visible}>
      <p>{t("chunk.updated")}</p>
      <button type="button" onClick={() => window.location.reload()}>
        {t("chunk.refresh")}
      </button>
      <button type="button" className="ghost" aria-label={t("chunk.dismiss")} onClick={() => setVisible(false)}>
        ×
      </button>
    </div>
  );
}
