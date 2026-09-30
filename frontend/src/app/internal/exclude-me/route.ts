import { decideExcludeMe, publicHost } from "@/lib/excludeMe";
import type { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

export function GET(request: NextRequest): Response {
  const host = publicHost(request.headers.get("host") || "", request.headers.get("x-forwarded-host") || "");
  const proto = request.headers.get("x-forwarded-proto") || request.nextUrl.protocol.replace(":", "");
  const decision = decideExcludeMe({
    providedToken: request.nextUrl.searchParams.get("token") || "",
    revoke: request.nextUrl.searchParams.get("revoke") === "1",
    expectedToken: process.env.ANALYTICS_EXCLUDE_ME_TOKEN || "",
    host,
    proto,
  });
  return new Response(decision.body, {
    status: decision.status,
    headers: decision.headers,
  });
}
