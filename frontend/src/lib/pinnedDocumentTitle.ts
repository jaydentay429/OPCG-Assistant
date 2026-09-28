"use client";

import { useLayoutEffect } from "react";
import type { Lang } from "@/lib/i18n";

/**
 * Homepage `<title>` in the server HTML stays the Traditional string from
 * `app/page.tsx`. The client pins the current language after that HTML loads.
 */
export const HOME_DOCUMENT_TITLES: Record<Lang, string> = {
  "zh-Hant": "OPCG 卡牌助手 (optcgassistant) | OPCG Assistant 卡牌搜索・構築・賽事卡組",
  "zh-Hans": "OPCG 卡牌助手 (optcgassistant) | OPCG Assistant 卡牌搜索・构筑・赛事卡组",
  en: "OPCG Card Assistant (optcgassistant) | OPCG Assistant Card Search, Deck Building, Tournament Decks",
};

export function homeDocumentTitle(lang: Lang): string {
  return HOME_DOCUMENT_TITLES[lang] ?? HOME_DOCUMENT_TITLES["zh-Hant"];
}

/**
 * Keep `document.title` on `title` after Next streams metadata.
 *
 * `generateMetadata` always builds the default Traditional title. For normal
 * browsers Next streams that into `<title>` and React writes the text node
 * directly (not via the `document.title` setter), which replaces a localized
 * title the page just set. Watching the title node and writing it back leaves
 * the server HTML `<title>` unchanged.
 */
export function usePinnedDocumentTitle(title: string | null | undefined): void {
  useLayoutEffect(() => {
    const next = String(title || "").trim();
    if (!next) return;

    let applying = false;
    const apply = () => {
      if (applying || document.title === next) return;
      applying = true;
      try {
        document.title = next;
      } finally {
        applying = false;
      }
    };

    apply();

    const head = document.head;
    if (!head) return;

    let titleEl: Element | null = null;
    const titleObserver = new MutationObserver(apply);
    const watchTitle = () => {
      const el = document.querySelector("title");
      if (el === titleEl) return;
      titleObserver.disconnect();
      titleEl = el;
      if (!el) return;
      titleObserver.observe(el, {
        subtree: true,
        childList: true,
        characterData: true,
      });
    };

    const headObserver = new MutationObserver(() => {
      watchTitle();
      apply();
    });
    watchTitle();
    headObserver.observe(head, { childList: true });

    return () => {
      titleObserver.disconnect();
      headObserver.disconnect();
    };
  }, [title]);
}
