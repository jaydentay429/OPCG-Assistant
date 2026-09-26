/**
 * Redirect targets for middleware.
 *
 * Behind Caddy, Next sees the incoming request as localhost:3000
 * (`request.url` / `nextUrl` host, and sometimes the Host header).
 * Building Location from those values publishes https://localhost:3000/...
 * to clients. Location is therefore always an absolute URL on the public
 * site origin, never the request host.
 */
export const CANONICAL_ORIGIN = (
  process.env.NEXT_PUBLIC_SITE_URL || "https://optcgassistant.com"
).replace(/\/$/, "");

export type RedirectPlan = {
  location: string;
  status: 301 | 308;
};

/** Absolute public URL. `pathname` must start with `/`; `search` is `?a=b` or empty. */
export function siteAbsoluteUrl(pathname: string, search = ""): string {
  const path = pathname.startsWith("/") ? pathname : `/${pathname}`;
  const query = search ? (search.startsWith("?") ? search : `?${search}`) : "";
  return new URL(`${CANONICAL_ORIGIN}${path}${query}`).href;
}

const CARD_PATH = /^\/cards\/([^/]+)\/?$/;

/**
 * Canonical card URLs are uppercase and have no trailing slash.
 * Wrong case and/or a trailing slash 301 once to that path, keeping the query.
 * Other trailing slashes 308 to the slash-less path (Next's default).
 * Already-canonical paths return null.
 */
export function canonicalRedirect(pathname: string, search = ""): RedirectPlan | null {
  const card = CARD_PATH.exec(pathname);
  if (card) {
    let raw = card[1];
    try {
      raw = decodeURIComponent(raw);
    } catch {
      return null;
    }
    const canonicalId = raw.toUpperCase();
    if (!canonicalId || canonicalId === "." || canonicalId === ".." || /[\u0000-\u001f\\/]/.test(canonicalId)) {
      return null;
    }
    const targetPath = `/cards/${canonicalId}`;
    if (pathname === targetPath) return null;
    return { location: siteAbsoluteUrl(targetPath, search), status: 301 };
  }

  if (pathname.length > 1 && pathname.endsWith("/")) {
    const stripped = pathname.replace(/\/+$/, "") || "/";
    if (stripped !== pathname) {
      return { location: siteAbsoluteUrl(stripped, search), status: 308 };
    }
  }
  return null;
}
