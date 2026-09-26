/**
 * Redirect targets for middleware.
 *
 * Behind Caddy, Next sees the incoming request as localhost:3000
 * (`request.url` / `nextUrl` host, and sometimes the Host header).
 * Building Location from those values publishes https://localhost:3000/...
 * to clients. Location is therefore always an absolute URL on the public
 * site origin, never the request host.
 */
export const PUBLIC_SITE_ORIGIN = "https://optcgassistant.com";

/**
 * Public origin for redirects. A missing value, or one that points at
 * localhost / 127.0.0.1, falls back to the production site so a bad build
 * env cannot publish the proxy host again.
 */
export function canonicalOriginFrom(raw: string | undefined | null): string {
  const value = String(raw ?? "").trim().replace(/\/$/, "");
  if (!value || /localhost|127\.0\.0\.1/i.test(value)) return PUBLIC_SITE_ORIGIN;
  return value;
}

export const CANONICAL_ORIGIN = canonicalOriginFrom(process.env.NEXT_PUBLIC_SITE_URL);

export type RedirectPlan = {
  location: string;
  status: 301 | 308;
};

/** Absolute public URL. `pathname` is used as-is; `search` is `?a=b` or empty. */
export function siteAbsoluteUrl(pathname: string, search = ""): string {
  const path = pathname.startsWith("/") ? pathname : `/${pathname}`;
  const query = search ? (search.startsWith("?") ? search : `?${search}`) : "";
  return `${CANONICAL_ORIGIN}${path}${query}`;
}

const CARD_PATH = /^\/cards\/([^/]+)\/?$/;
/** Card ids we will case-fold. Anything else (spaces, `%`, unicode) must not redirect. */
const SAFE_CARD_ID = /^[A-Za-z0-9_-]+$/;

/**
 * Canonical card URLs are uppercase and have no trailing slash.
 * Only a raw path segment matching [A-Za-z0-9_-]+ is case-folded. The segment
 * is not decoded: decoding `%20` / `%E8%...` and uppercasing produces a path
 * that `new URL()` encodes back to the request, which 301s forever.
 * Other trailing slashes 308 once to the slash-less path. Already-canonical
 * paths, and card ids outside the safe set with no trailing slash, return null.
 */
export function canonicalRedirect(pathname: string, search = ""): RedirectPlan | null {
  const card = CARD_PATH.exec(pathname);
  if (card) {
    const segment = card[1];
    if (SAFE_CARD_ID.test(segment)) {
      const targetPath = `/cards/${segment.toUpperCase()}`;
      if (pathname === targetPath) return null;
      return { location: siteAbsoluteUrl(targetPath, search), status: 301 };
    }
    // Unsafe id: do not case-redirect. Drop a trailing slash with one 308.
    if (pathname.length > 1 && pathname.endsWith("/")) {
      const stripped = pathname.replace(/\/+$/, "") || "/";
      if (stripped !== pathname) {
        return { location: siteAbsoluteUrl(stripped, search), status: 308 };
      }
    }
    return null;
  }

  if (pathname.length > 1 && pathname.endsWith("/")) {
    const stripped = pathname.replace(/\/+$/, "") || "/";
    if (stripped !== pathname) {
      return { location: siteAbsoluteUrl(stripped, search), status: 308 };
    }
  }
  return null;
}
