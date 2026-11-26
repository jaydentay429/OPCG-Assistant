import en from "@/locales/en";
import zhHans from "@/locales/zh-Hans";
import zhHant from "@/locales/zh-Hant";

/** Server-safe dictionary lookup (no "use client"), shared with the I18n provider. */
export type Lang = "zh-Hant" | "zh-Hans" | "en";

type Dict = Record<string, string>;

const DICTS: Record<Lang, Dict> = {
  "zh-Hant": zhHant,
  "zh-Hans": zhHans,
  en,
};

/** Same lookup the provider uses, so error UI can render without the provider. */
export function translate(lang: Lang, key: string, vars?: Record<string, string | number>): string {
  // English must never fall back to Chinese chrome strings.
  let s =
    DICTS[lang][key] ??
    (lang === "zh-Hans" ? DICTS["zh-Hant"][key] : undefined) ??
    (lang === "en" ? undefined : DICTS.en[key]) ??
    key;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      s = s.replaceAll(`{${k}}`, String(v));
    }
  }
  return s;
}

