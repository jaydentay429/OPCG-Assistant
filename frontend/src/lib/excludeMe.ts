/** Unlisted "don't count this device" cookie. The token stays in the query string. */

export const EXCLUDE_COOKIE_NAME = "opcg_exclude_me";
export const EXCLUDE_COOKIE_VALUE = "1";
/** Chrome drops persistent cookies past about 400 days. */
export const EXCLUDE_COOKIE_MAX_AGE_SECONDS = 400 * 24 * 60 * 60;

const STATS_DOMAIN = "optcgassistant.com";

export function hostName(hostHeader: string): string {
  const first = hostHeader.split(",")[0]?.trim() ?? "";
  if (first.startsWith("[")) {
    const end = first.indexOf("]");
    if (end > 1) return first.slice(1, end).toLowerCase();
  }
  return first.split(":")[0]?.toLowerCase() ?? "";
}

export function isLocalHost(hostHeader: string): boolean {
  const name = hostName(hostHeader);
  return name === "localhost" || name === "127.0.0.1" || name === "::1";
}

/**
 * Cookie domain covering the site and stats subdomains (api, www).
 * Other hosts get a host-only cookie so a spoofed Domain cannot stick.
 */
export function cookieDomainForHost(hostHeader: string): string | undefined {
  const name = hostName(hostHeader);
  if (name === STATS_DOMAIN || name.endsWith(`.${STATS_DOMAIN}`)) {
    return `.${STATS_DOMAIN}`;
  }
  return undefined;
}

/** Secure on the public site. Plain http localhost cannot store a Secure cookie. */
export function cookieSecureForRequest(protoHeader: string, hostHeader: string): boolean {
  const proto = protoHeader.split(",")[0]?.trim().replace(/:$/, "").toLowerCase() ?? "";
  if (proto === "https") return true;
  if (isLocalHost(hostHeader)) return false;
  return true;
}

/**
 * Behind Caddy, Host is the public name. If the app only sees localhost,
 * use the forwarded host so the cookie still covers the public domain.
 */
export function publicHost(hostHeader: string, forwardedHost: string): string {
  if (!isLocalHost(hostHeader)) return hostHeader.split(",")[0]?.trim() ?? hostHeader;
  const forwarded = forwardedHost.split(",")[0]?.trim() ?? "";
  return forwarded || (hostHeader.split(",")[0]?.trim() ?? hostHeader);
}

export function buildExcludeCookie(opts: { revoke: boolean; host: string; proto: string }): string {
  const parts = [
    opts.revoke ? `${EXCLUDE_COOKIE_NAME}=` : `${EXCLUDE_COOKIE_NAME}=${EXCLUDE_COOKIE_VALUE}`,
    `Max-Age=${opts.revoke ? 0 : EXCLUDE_COOKIE_MAX_AGE_SECONDS}`,
    "Path=/",
    "HttpOnly",
    "SameSite=Lax",
  ];
  if (cookieSecureForRequest(opts.proto, opts.host)) parts.push("Secure");
  const domain = cookieDomainForHost(opts.host);
  if (domain) parts.push(`Domain=${domain}`);
  return parts.join("; ");
}

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export type ExcludeDecision = {
  status: 200 | 404;
  body: string;
  headers: Record<string, string>;
};

export function tokenMatches(provided: string, expected: string): boolean {
  const want = expected.trim();
  if (!want || provided.length !== want.length) return false;
  let mismatch = 0;
  for (let i = 0; i < want.length; i += 1) {
    mismatch |= provided.charCodeAt(i) ^ want.charCodeAt(i);
  }
  return mismatch === 0;
}

export function decideExcludeMe(input: {
  providedToken: string;
  revoke: boolean;
  expectedToken: string;
  host: string;
  proto: string;
}): ExcludeDecision {
  const robots = {
    "X-Robots-Tag": "noindex, nofollow",
    "Cache-Control": "no-store",
  };
  if (!tokenMatches(input.providedToken, input.expectedToken)) {
    return {
      status: 404,
      body: "Not Found",
      headers: { ...robots, "Content-Type": "text/plain; charset=utf-8" },
    };
  }
  const sentence = input.revoke ? "此设备已恢复计入统计" : "此设备已不计入统计";
  const token = encodeURIComponent(input.providedToken);
  const action = input.revoke
    ? `<p><a href="/internal/exclude-me?token=${token}">重新排除此设备</a></p>`
    : `<p><a href="/internal/exclude-me?token=${token}&amp;revoke=1">撤销</a></p>`;
  const body = `<!DOCTYPE html>
<html lang="zh-Hans">
<head>
<meta charset="utf-8">
<meta name="robots" content="noindex, nofollow">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escapeHtml(sentence)}</title>
<style>
  body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: #0b1220; color: #e8eefc; font: 16px/1.5 system-ui, sans-serif; }
  main { max-width: 28rem; padding: 2rem; }
  a { color: #8eb6ff; }
</style>
</head>
<body>
<main>
  <p>${escapeHtml(sentence)}</p>
  ${action}
</main>
</body>
</html>`;
  return {
    status: 200,
    body,
    headers: {
      ...robots,
      "Content-Type": "text/html; charset=utf-8",
      "Set-Cookie": buildExcludeCookie({
        revoke: input.revoke,
        host: input.host,
        proto: input.proto,
      }),
    },
  };
}
