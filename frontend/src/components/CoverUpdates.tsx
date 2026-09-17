"use client";

import Link from "next/link";
import { useId, useState } from "react";
import { useI18n } from "@/lib/i18n";
import { formatUpdateDate, latestSiteUpdates } from "@/lib/siteUpdates";
import { markTabNavScrollReset } from "@/lib/scrollRestore";

export function CoverUpdates() {
  const { t, lang } = useI18n();
  const items = latestSiteUpdates();
  const [open, setOpen] = useState(false);
  const panelId = useId();

  return (
    <aside className={`cover-updates${open ? " is-open" : " is-collapsed"}`} aria-label={t("cover.updates_aria")}>
      <button
        type="button"
        className="cover-updates-toggle"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="cover-updates-head">
          <span className="cover-updates-kicker">{t("cover.updates_kicker")}</span>
          <span className="cover-updates-title">{t("cover.updates_title")}</span>
        </span>
        <span className="cover-updates-toggle-meta">
          <span className="cover-updates-count">{t("cover.updates_count", { n: items.length })}</span>
          <span className="cover-updates-chevron" aria-hidden>
            ▾
          </span>
        </span>
      </button>
      <div className="cover-updates-panel" id={panelId} hidden={!open}>
        <ul className="cover-updates-list">
          {items.map((item) => {
            const kindLabel = item.kind === "fix" ? t("cover.updates_fix") : t("cover.updates_feature");
            const inner = (
              <>
                <div className="cover-updates-meta">
                  <span className={`cover-updates-kind is-${item.kind}`}>{kindLabel}</span>
                  <time dateTime={item.date}>{formatUpdateDate(item.date, lang)}</time>
                </div>
                <p className="cover-updates-item-title">{item.title[lang]}</p>
                <p className="cover-updates-item-body">{item.body[lang]}</p>
              </>
            );
            return (
              <li key={item.id}>
                {item.href ? (
                  <Link
                    href={item.href}
                    className="cover-updates-item is-link"
                    onClick={() => markTabNavScrollReset()}
                  >
                    {inner}
                  </Link>
                ) : (
                  <div className="cover-updates-item">{inner}</div>
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </aside>
  );
}
