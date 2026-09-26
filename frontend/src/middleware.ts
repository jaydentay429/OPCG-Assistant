import { NextResponse, type NextRequest } from "next/server";

/** Citation / training crawlers to count. Failures are dropped — never block the page. */
const AI_BOTS: Array<[string, RegExp]> = [
  ["GPTBot", /GPTBot/i],
  ["ChatGPT-User", /ChatGPT-User/i],
  ["OAI-SearchBot", /OAI-SearchBot/i],
  ["PerplexityBot", /PerplexityBot/i],
  ["ClaudeBot", /ClaudeBot/i],
  ["Google-Extended", /Google-Extended/i],
];

function ingestBase(): string {
  const raw = process.env.OPCG_ANALYTICS_INGEST_URL || "http://127.0.0.1:8000";
  return raw.replace(/\/$/, "");
}

/**
 * Canonical card URLs are uppercase and have no trailing slash
 * (`/cards/ST18-005-P2`). Wrong case and/or a trailing slash 301 once to that
 * path. nextUrl.clone() keeps the request's trailingSlash flag and would put
 * the slash back, so this builds a plain URL. Already-canonical paths are
 * left alone. Search params are kept.
 */
function redirectNonCanonicalCardUrl(request: NextRequest): NextResponse | null {
  const url = new URL(request.url);
  const match = url.pathname.match(/^\/cards\/([^/]+)\/?$/);
  if (!match) return null;
  let raw = match[1];
  try {
    raw = decodeURIComponent(raw);
  } catch {
    return null;
  }
  const canonical = raw.toUpperCase();
  if (!canonical) return null;
  const target = `/cards/${canonical}`;
  if (url.pathname === target) return null;
  url.pathname = target;
  return NextResponse.redirect(url, 301);
}

/**
 * next.config sets skipTrailingSlashRedirect so the card redirect above can
 * see the slash and collapse case + slash into one hop. Other paths keep
 * Next's default: one 308 that drops a trailing slash.
 */
function redirectTrailingSlash(request: NextRequest): NextResponse | null {
  const url = new URL(request.url);
  if (url.pathname.length <= 1 || !url.pathname.endsWith("/")) return null;
  url.pathname = url.pathname.replace(/\/+$/, "") || "/";
  return NextResponse.redirect(url, 308);
}

export function middleware(request: NextRequest) {
  const ua = request.headers.get("user-agent") || "";
  const bot = AI_BOTS.find(([, re]) => re.test(ua))?.[0];
  if (bot) {
    const path = request.nextUrl.pathname.slice(0, 300) || "/";
    void fetch(`${ingestBase()}/analytics/ai-crawl`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ bot, path }),
      keepalive: true,
    }).catch(() => {});
  }
  const cardRedirect = redirectNonCanonicalCardUrl(request);
  if (cardRedirect) return cardRedirect;
  const slashRedirect = redirectTrailingSlash(request);
  if (slashRedirect) return slashRedirect;
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|packs/|.*\\.(?:png|jpg|jpeg|gif|webp|svg|ico|css|js|map|woff2?)$).*)"],
};
