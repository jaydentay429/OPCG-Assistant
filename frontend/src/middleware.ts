import { NextResponse, type NextRequest } from "next/server";
import { canonicalRedirect } from "./lib/siteRedirect";

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
  // Path and query only. Location is built from the public site origin inside
  // canonicalRedirect — never from request.url, nextUrl, or the Host header.
  const plan = canonicalRedirect(request.nextUrl.pathname, request.nextUrl.search);
  if (plan) return NextResponse.redirect(plan.location, plan.status);
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|packs/|.*\\.(?:png|jpg|jpeg|gif|webp|svg|ico|css|js|map|woff2?)$).*)"],
};
