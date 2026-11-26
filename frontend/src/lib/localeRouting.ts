/**
 * Language URLs.
 *
 * Traditional Chinese (the default) keeps the existing unprefixed paths.
 * Simplified Chinese lives under /zh-hans and English under /en. Middleware
 * rewrites a prefixed request to the unprefixed route and passes the language
 * in a request header, so every route is written once.
 *
 * Only LOCALIZED_ROUTES get prefixed copies. A prefix on any other path
 * redirects once to the unprefixed path (no loop: the target has no prefix).
 */

export type UrlLang = "zh-Hant" | "zh-Hans" | "en";

export const LANG_HEADER = "x-opcg-lang";

export const LANG_PREFIX: Record<UrlLang, string> = {
  "zh-Hant": "",
  "zh-Hans": "/zh-hans",
  en: "/en",
};

const PREFIX_TO_LANG: Array<[string, UrlLang]> = [
  ["/zh-hans", "zh-Hans"],
  ["/en", "en"],
];

/** Exact paths and path prefixes (ending in "/") that have /en and /zh-hans copies. */
const LOCALIZED_EXACT = new Set([
  "/",
  "/search",
  "/builder",
  "/tournaments",
  "/prices",
  "/sets",
  "/leaders",
]);
const LOCALIZED_PREFIXES = ["/cards/", "/sets/", "/leaders/"];

export function isUrlLang(value: unknown): value is UrlLang {
  return value === "zh-Hant" || value === "zh-Hans" || value === "en";
}

/** Language named by a path prefix, or null for an unprefixed path. */
export function langFromPathname(pathname: string): UrlLang | null {
  const path = String(pathname || "");
  for (const [prefix, lang] of PREFIX_TO_LANG) {
    if (path === prefix || path.startsWith(`${prefix}/`)) return lang;
  }
  return null;
}

/** Path without its language prefix ("/en/cards/X" → "/cards/X", "/en" → "/"). */
export function stripLangPrefix(pathname: string): string {
  const path = String(pathname || "") || "/";
  for (const [prefix] of PREFIX_TO_LANG) {
    if (path === prefix) return "/";
    if (path.startsWith(`${prefix}/`)) return path.slice(prefix.length) || "/";
  }
  return path;
}

export function isLocalizedRoute(pathname: string): boolean {
  const path = stripLangPrefix(String(pathname || "").split(/[?#]/)[0] || "/");
  if (LOCALIZED_EXACT.has(path)) return true;
  return LOCALIZED_PREFIXES.some((p) => path.startsWith(p) && path.length > p.length);
}

/**
 * Href for `path` in `lang`. Query and hash are kept. Paths without language
 * copies, absolute URLs, and anchors are returned unchanged.
 */
export function localizedPath(path: string, lang: UrlLang): string {
  const raw = String(path || "");
  if (!raw.startsWith("/") || raw.startsWith("//")) return raw;
  const cut = raw.search(/[?#]/);
  const pathname = cut === -1 ? raw : raw.slice(0, cut);
  const rest = cut === -1 ? "" : raw.slice(cut);
  const bare = stripLangPrefix(pathname);
  if (!isLocalizedRoute(bare)) return `${bare}${rest}`;
  const prefix = LANG_PREFIX[lang] || "";
  if (!prefix) return `${bare}${rest}`;
  return `${prefix}${bare === "/" ? "" : bare}${rest}`;
}

/** hreflang → absolute URL for a localized page. `x-default` is the Traditional URL. */
export function hreflangAlternates(path: string, origin: string): Record<string, string> {
  const base = origin.replace(/\/$/, "");
  const hant = `${base}${localizedPath(path, "zh-Hant")}`;
  const hans = `${base}${localizedPath(path, "zh-Hans")}`;
  const en = `${base}${localizedPath(path, "en")}`;
  return {
    "zh-Hant": hant,
    "zh-HK": hant,
    "zh-TW": hant,
    "zh-Hans": hans,
    "zh-CN": hans,
    en,
    "x-default": hant,
  };
}

/** `<html lang>` value per UI language. */
export function htmlLangAttr(lang: UrlLang): string {
  return lang === "en" ? "en" : lang === "zh-Hans" ? "zh-Hans" : "zh-Hant";
}

/** Open Graph locale per UI language. */
export function ogLocale(lang: UrlLang): string {
  return lang === "en" ? "en_US" : lang === "zh-Hans" ? "zh_CN" : "zh_HK";
}

/**
 * Absolute URL for an internal middleware rewrite to `pathname`.
 *
 * Next's NextURL reports a loopback listen address (HOSTNAME=127.0.0.1 in
 * opcg-web.service) as "localhost", but the router compares the rewrite with
 * the real listen origin. A mismatch makes Next proxy the rewrite as an
 * external request, which loses the x-opcg-lang request header. Put the listen
 * address back so the rewrite stays internal.
 */
export function internalRewriteUrl(requestUrl: string, pathname: string, listenHost?: string): URL {
  const url = new URL(requestUrl);
  url.pathname = pathname;
  const host = String(listenHost || "").trim();
  if (url.hostname === "localhost" && host && host !== "localhost") {
    if (/^127(?:\.\d{1,3}){3}$/.test(host)) url.hostname = host;
    else if (host === "::1" || host === "[::1]") url.hostname = "[::1]";
  }
  return url;
}
