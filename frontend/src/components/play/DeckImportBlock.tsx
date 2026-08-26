"use client";

import { useI18n } from "@/lib/i18n";

type Props = {
  label: string;
  value: string;
  onChange: (v: string) => void;
  onApply: () => void;
  busy: boolean;
  importing: boolean;
  appliedLabel: string | null;
};

export function DeckImportBlock({
  label,
  value,
  onChange,
  onApply,
  busy,
  importing,
  appliedLabel,
}: Props) {
  const { t } = useI18n();

  return (
    <div className="play-import">
      {appliedLabel ? <p className="muted play-import-applied">{appliedLabel}</p> : null}
      <details className="play-import-details">
        <summary className="play-import-toggle">
          <span>{label}</span>
          <span className="play-import-toggle-hint when-closed">{t("deck.section_expand")}</span>
          <span className="play-import-toggle-hint when-open">{t("deck.section_collapse")}</span>
        </summary>
        <div className="play-import-body">
          <label className="play-field">
            <textarea
              value={value}
              onChange={(e) => onChange(e.target.value)}
              placeholder={t("deck.import_ph")}
              rows={4}
              disabled={busy || importing}
            />
          </label>
          <div className="play-actions">
            <button
              type="button"
              className="secondary"
              disabled={busy || importing || !value.trim()}
              onClick={onApply}
            >
              {importing ? t("deck.importing") : t("play.import_apply")}
            </button>
          </div>
        </div>
      </details>
    </div>
  );
}
