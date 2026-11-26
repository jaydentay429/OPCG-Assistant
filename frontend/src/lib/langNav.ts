"use client";

import { useRouter } from "next/navigation";
import { useCallback } from "react";
import { useI18n, type Lang } from "./i18n";
import { isLocalizedRoute, localizedPath, stripLangPrefix } from "./localeRouting";

/** `href` for internal links in the current UI language (/en, /zh-hans copies). */
export function useLocalizedHref(): (path: string) => string {
  const { lang } = useI18n();
  return useCallback((path: string) => localizedPath(path, lang), [lang]);
}

/**
 * Change the UI language. On a page that has language URLs, also move to that
 * URL so the address, canonical and server HTML match what is on screen.
 */
export function useSwitchLang(): (next: Lang) => void {
  const { setLang } = useI18n();
  const router = useRouter();
  return useCallback(
    (next: Lang) => {
      setLang(next);
      if (typeof window === "undefined") return;
      const { pathname, search, hash } = window.location;
      const bare = stripLangPrefix(pathname);
      if (!isLocalizedRoute(bare)) return;
      const target = localizedPath(`${bare}${search}${hash}`, next);
      if (target !== `${pathname}${search}${hash}`) router.push(target, { scroll: false });
    },
    [setLang, router],
  );
}
