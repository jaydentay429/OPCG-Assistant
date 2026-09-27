/** Retry-After on a card page whose API call did not get a definitive answer. */
export const CARD_UNAVAILABLE_RETRY_AFTER = "10";

/**
 * True for the card detail route only. Language-prefixed paths are not card
 * pages in this app; they must keep the normal not-found response.
 */
export function isCardDetailPath(url: string | undefined | null): boolean {
  const path = String(url || "").split("?")[0] || "";
  return /^\/cards\/[^/]+\/?$/.test(path);
}

/** A server failure status. 404 stays a 404. */
export function isServerErrorStatus(status: number): boolean {
  return status >= 500 && status <= 599;
}

/**
 * Next's error document adds this tag for every status above 400, including
 * 500. On a card-page outage that tag must not be sent: a 5xx is a temporary
 * failure, and noindex is what a crawler treats as "drop this URL".
 * A robots meta that does not say noindex is left in place.
 */
export function stripServerErrorNoindex(html: string): string {
  return html.replace(/<meta\b[^>]*>/gi, (tag) => {
    if (!/\bname\s*=\s*["']robots["']/i.test(tag)) return tag;
    const content = /\bcontent\s*=\s*["']([^"']*)["']/i.exec(tag)?.[1] ?? "";
    if (/\bnoindex\b/i.test(content)) return "";
    return tag;
  });
}

/** Rewrite a buffered card-page error body. Non-HTML payloads are unchanged. */
export function rewriteCardServerErrorBody(body: Buffer): Buffer {
  const head = body.subarray(0, 1500).toString("utf8");
  if (!/<!DOCTYPE|<html|<meta/i.test(head)) return body;
  const text = body.toString("utf8");
  const next = stripServerErrorNoindex(text);
  if (next === text) return body;
  return Buffer.from(next);
}
