"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { translate } from "@/lib/translate";
import { usePathname } from "next/navigation";
import { OPENCC_READY_EVENT } from "@/lib/openccEvents";
import { htmlLangAttr, langFromPathname } from "@/lib/localeRouting";
import type { Lang } from "@/lib/translate";

export type { Lang };
export { translate };

export const LANG_OPTIONS: { id: Lang; labelKey: string }[] = [
  { id: "zh-Hant", labelKey: "lang.zh_hant" },
  { id: "zh-Hans", labelKey: "lang.zh_hans" },
  { id: "en", labelKey: "lang.en" },
];

const LANG_KEY = "opcg_lang";
const DEFAULT_LANG: Lang = "zh-Hant";

function normalizeLang(raw: string | null | undefined): Lang | null {
  if (!raw) return null;
  if (raw === "zh-Hant" || raw === "zh-Hans" || raw === "en") return raw;
  // Migrate legacy values.
  if (raw === "zh" || raw === "zh-TW" || raw === "zh-HK") return "zh-Hant";
  if (raw === "zh-CN" || raw === "zh-Hans-CN") return "zh-Hans";
  return null;
}

type I18nCtx = {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
  /** Increments when an OpenCC dictionary becomes ready so cached filters can refresh. */
  openccRev: number;
};

const Ctx = createContext<I18nCtx | null>(null);

export function readStoredLang(): Lang {
  if (typeof window === "undefined") return DEFAULT_LANG;
  try {
    return normalizeLang(localStorage.getItem(LANG_KEY)) ?? DEFAULT_LANG;
  } catch {
    return DEFAULT_LANG;
  }
}

/**
 * `initialLang` comes from the server (the URL prefix), so the first render and
 * the SSR HTML are in the page's language. A prefixed URL (/en, /zh-hans) pins
 * the language and is remembered. An unprefixed URL keeps the old behaviour:
 * Traditional on the server, then the saved choice on the client.
 */
export function I18nProvider({
  children,
  initialLang = DEFAULT_LANG,
}: {
  children: ReactNode;
  initialLang?: Lang;
}) {
  const [lang, setLangState] = useState<Lang>(initialLang);
  const pathname = usePathname();
  // Bumps when an OpenCC dictionary finishes loading so visible text can replace
  // the original string. The provider does not import the dictionaries themselves.
  const [openccRev, setOpenccRev] = useState(0);

  useEffect(() => {
    const bump = () => setOpenccRev((n) => n + 1);
    window.addEventListener(OPENCC_READY_EVENT, bump);
    return () => window.removeEventListener(OPENCC_READY_EVENT, bump);
  }, []);

  useEffect(() => {
    const fromUrl =
      typeof window !== "undefined" ? langFromPathname(window.location.pathname) : null;
    if (fromUrl) {
      setLangState(fromUrl);
      try {
        localStorage.setItem(LANG_KEY, fromUrl);
      } catch {
        /* ignore */
      }
      return;
    }
    try {
      const saved = normalizeLang(localStorage.getItem(LANG_KEY));
      if (saved) setLangState(saved);
    } catch {
      /* ignore */
    }
  }, [pathname]);

  useEffect(() => {
    if (typeof document !== "undefined") {
      document.documentElement.lang = htmlLangAttr(lang);
    }
  }, [lang]);

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try {
      localStorage.setItem(LANG_KEY, l);
    } catch {
      /* ignore */
    }
  }, []);

  const t = useCallback(
    (key: string, vars?: Record<string, string | number>) => translate(lang, key, vars),
    [lang],
  );

  const value = useMemo<I18nCtx>(() => {
    return { lang, setLang, t, openccRev };
  }, [lang, setLang, t, openccRev]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useI18n() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useI18n outside provider");
  return ctx;
}

/** Null when the root layout (and its provider) failed to mount. */
export function useOptionalI18n(): I18nCtx | null {
  return useContext(Ctx);
}
