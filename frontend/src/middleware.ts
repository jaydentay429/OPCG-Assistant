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
 * Real card URLs are uppercase (`/cards/OP01-065`). A lowercase or mixed-case
 * id 301s there. Already-uppercase paths are left alone, so this cannot loop.
 * Search params are kept by cloning the request URL.
 */
function redirectNonCanonicalCardCasing(request: NextRequest): NextResponse | null {
  const match = request.nextUrl.pathname.match(/^\/cards\/([^/]+)$/);
  if (!match) return null;
  let raw = match[1];
  try {
    raw = decodeURIComponent(raw);
  } catch {
    return null;
  }
  const canonical = raw.toUpperCase();
  if (!canonical || canonical === raw) return null;
  const url = request.nextUrl.clone();
  url.pathname = `/cards/${canonical}`;
  return NextResponse.redirect(url, 301);
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
  const casingRedirect = redirectNonCanonicalCardCasing(request);
  if (casingRedirect) return casingRedirect;
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|packs/|.*\\.(?:png|jpg|jpeg|gif|webp|svg|ico|css|js|map|woff2?)$).*)"],
};
