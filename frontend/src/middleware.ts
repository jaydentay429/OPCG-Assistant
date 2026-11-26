import { NextResponse, type NextRequest } from "next/server";
import {
  LANG_HEADER,
  LANG_PREFIX,
  internalRewriteUrl,
  isLocalizedRoute,
  langFromPathname,
  stripLangPrefix,
} from "./lib/localeRouting";
import { canonicalRedirect, siteAbsoluteUrl } from "./lib/siteRedirect";

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
  const pathname = request.nextUrl.pathname;
  const search = request.nextUrl.search;

  // Old-style explicit Traditional prefix: one 301 to the unprefixed URL.
  if (/^\/zh-hant(?:\/|$)/i.test(pathname)) {
    const bare = pathname.replace(/^\/zh-hant/i, "") || "/";
    return NextResponse.redirect(siteAbsoluteUrl(bare, search), 301);
  }

  const urlLang = langFromPathname(pathname);
  if (urlLang) {
    const bare = stripLangPrefix(pathname);
    // A prefix on a page without language copies goes to the plain page once.
    const bareNoSlash = bare.replace(/\/+$/, "") || "/";
    if (!isLocalizedRoute(bareNoSlash)) {
      return NextResponse.redirect(siteAbsoluteUrl(bareNoSlash, search), 308);
    }
    // "/en/" → "/en", "/en/cards/op01-001" → "/en/cards/OP01-001" (single hop).
    const plan = canonicalRedirect(bare, search);
    if (plan) {
      const target = new URL(plan.location);
      const prefix = LANG_PREFIX[urlLang];
      const path = target.pathname === "/" ? prefix : `${prefix}${target.pathname}`;
      return NextResponse.redirect(siteAbsoluteUrl(path, target.search), plan.status);
    }
    if (pathname.endsWith("/") && pathname.length > 1) {
      return NextResponse.redirect(siteAbsoluteUrl(pathname.replace(/\/+$/, ""), search), 308);
    }
    const headers = new Headers(request.headers);
    headers.set(LANG_HEADER, urlLang);
    const url = internalRewriteUrl(request.url, bare, process.env.HOSTNAME);
    return NextResponse.rewrite(url, { request: { headers } });
  }

  // Path and query only. Location is built from the public site origin inside
  // canonicalRedirect — never from request.url, nextUrl, or the Host header.
  const plan = canonicalRedirect(pathname, search);
  if (plan) return NextResponse.redirect(plan.location, plan.status);
  // Strip any client-supplied language header on unprefixed URLs.
  if (request.headers.has(LANG_HEADER)) {
    const headers = new Headers(request.headers);
    headers.delete(LANG_HEADER);
    return NextResponse.next({ request: { headers } });
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|packs/|.*\\.(?:png|jpg|jpeg|gif|webp|svg|ico|css|js|map|woff2?)$).*)"],
};
