import { PACKS_CDN_BASE, cardImageUrl } from "./api";
import { normalizeCardId } from "./cardId";
import { cardImageHash } from "./cardImageManifest";

const PUBLIC_CARD_IMAGE_HOST = "https://img.optcgassistant.com";

/**
 * Card-wall slots measured on /search: 60px CSS under the 900px breakpoint
 * (5 columns), 153px above it (7 columns). At 3x that is 180px, so the 200w
 * file wins on phones; at 2x desktop (306px) the 320w file wins.
 * Widths match scripts/generate_card_webp.py.
 */
export const CARD_WALL_IMAGE_SIZES = "(max-width: 900px) 60px, 153px";

const webpMisses = new Set<string>();

export function clearListWebpMisses(): void {
  webpMisses.clear();
}

/** Remember a WebP 404 so the next render of this id uses the PNG URL. */
export function noteListWebpMiss(cardId: string): void {
  const id = normalizeCardId(cardId);
  if (id) webpMisses.add(id);
}

export function hasListWebpMiss(cardId: string): boolean {
  const id = normalizeCardId(cardId);
  return id !== "" && webpMisses.has(id);
}

function cdnBase(): string {
  return PACKS_CDN_BASE || PUBLIC_CARD_IMAGE_HOST;
}

/** Object key shared with scripts/generate_card_webp.py. Hash is the PNG ?h=. */
export function cardWebpObjectKey(
  cardId: string,
  hash: string,
  kind: "w200" | "w320" | "full",
): string {
  const id = normalizeCardId(cardId);
  if (kind === "full") return `${id}.${hash}.webp`;
  return `${id}.${kind}.${hash}.webp`;
}

export function cardWebpUrl(cardId: string, hash: string, kind: "w200" | "w320" | "full"): string {
  const key = cardWebpObjectKey(cardId, hash, kind);
  return `${cdnBase()}/${encodeURIComponent(key)}?h=${hash}`;
}

export type ListCardImage = {
  src: string;
  srcSet?: string;
  sizes?: string;
  /** False means src is the existing PNG URL and srcSet must not be set. */
  webp: boolean;
};

/**
 * List-thumbnail request for the search card wall.
 * WebP is tried first. After a load error (or a remembered miss) the src is
 * the same PNG URL cardImageUrl already publishes, with no srcSet, so a
 * deploy that lands before the WebP upload cannot leave a broken image.
 * The full-size WebP key is not included; the card page still uses PNG.
 */
export function listCardImageAttrs(cardId: string, webpFailed = false): ListCardImage | null {
  const png = cardImageUrl(cardId);
  const hash = cardImageHash(cardId);
  if (!png || !hash) return null;
  if (webpFailed || hasListWebpMiss(cardId)) {
    return { src: png, webp: false };
  }
  const w200 = cardWebpUrl(cardId, hash, "w200");
  const w320 = cardWebpUrl(cardId, hash, "w320");
  return {
    src: w320,
    srcSet: `${w200} 200w, ${w320} 320w`,
    sizes: CARD_WALL_IMAGE_SIZES,
    webp: true,
  };
}
