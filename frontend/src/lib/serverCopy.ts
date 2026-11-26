import { localizedPath, type UrlLang } from "./localeRouting";
import { getRequestLang } from "./requestLang";
import { serverHansConverter } from "./serverHans";

export type ServerCopy = {
  lang: UrlLang;
  /** Traditional text, its English version; Simplified is converted from the Traditional text. */
  L: (hant: string, en: string) => string;
  /** Traditional → Simplified on /zh-hans, identity otherwise (card names, effects). */
  hans: (text: string) => string;
  /** Internal href in this page's language. */
  href: (path: string) => string;
};

/**
 * Copy helper for server components and metadata. Page text keeps one
 * Traditional source string; /zh-hans converts it with the same OpenCC
 * dictionaries the browser uses, and /en uses the English string.
 */
export async function serverCopy(langOverride?: UrlLang): Promise<ServerCopy> {
  const lang = langOverride ?? (await getRequestLang());
  const hans = await serverHansConverter(lang);
  return {
    lang,
    hans,
    L: (hant, en) => (lang === "en" ? en : lang === "zh-Hans" ? hans(hant) : hant),
    href: (path) => localizedPath(path, lang),
  };
}
