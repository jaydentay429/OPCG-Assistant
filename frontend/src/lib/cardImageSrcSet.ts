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

/**
 * Detail-page variant strip. Slots are about 56–80 CSS px, so 1x/2x pick the
 * 200w thumbnail and only a 3x screen steps up to 320w. Never the full PNG.
 */
export const DETAIL_THUMB_IMAGE_SIZES = "80px";

const listWebpMisses = new Set<string>();
const heroWebpMisses = new Set<string>();

export function clearListWebpMisses(): void {
  listWebpMisses.clear();
}

/** Remember a list-thumbnail WebP 404 so the next render of this id uses the PNG URL. */
export function noteListWebpMiss(cardId: string): void {
  const id = normalizeCardId(cardId);
  if (id) listWebpMisses.add(id);
}

export function hasListWebpMiss(cardId: string): boolean {
  const id = normalizeCardId(cardId);
  return id !== "" && listWebpMisses.has(id);
}

export function clearHeroWebpMisses(): void {
  heroWebpMisses.clear();
}

/** Remember a card-page hero WebP 404. Does not affect list thumbnails. */
export function noteHeroWebpMiss(cardId: string): void {
  const id = normalizeCardId(cardId);
  if (id) heroWebpMisses.add(id);
}

export function hasHeroWebpMiss(cardId: string): boolean {
  const id = normalizeCardId(cardId);
  return id !== "" && heroWebpMisses.has(id);
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
 * Thumbnail request for the search card wall and the card-page variant strip.
 * WebP is tried first. After a load error (or a remembered miss) the src is
 * the same PNG URL cardImageUrl already publishes, with no srcSet, so a
 * deploy that lands before the WebP upload cannot leave a broken image.
 * The full-size WebP key is not included; the card page hero requests that
 * object through heroCardImageAttrs.
 */
export function listCardImageAttrs(
  cardId: string,
  webpFailed = false,
  sizes: string = CARD_WALL_IMAGE_SIZES,
): ListCardImage | null {
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
    sizes,
    webp: true,
  };
}

/**
 * The `<img>` is already in the SSR HTML, so its error event can fire before
 * hydration attaches onError. A finished load with no pixels is that miss.
 * An image that has not finished yet, or that decoded, is not a miss.
 */
export function webpLoadAlreadyFailed(
  img: { complete: boolean; naturalWidth: number } | null | undefined,
): boolean {
  return !!img && img.complete && img.naturalWidth === 0;
}

/**
 * Card-detail main image. One full-size WebP (`{id}.{hash}.webp?h={hash}`),
 * the same object generate_card_webp.py uploads. After a load error the src
 * is the existing PNG URL with the same `?h=`. No srcSet: this is a single
 * file, not the list thumbnails. Variant ids keep their own hash and key.
 * Open Graph, Twitter, JSON-LD, and the sitemap stay on cardImageUrl (PNG).
 */
export function heroCardImageAttrs(cardId: string, webpFailed = false): ListCardImage | null {
  const png = cardImageUrl(cardId);
  const hash = cardImageHash(cardId);
  if (!png || !hash) return null;
  if (webpFailed || hasHeroWebpMiss(cardId)) {
    return { src: png, webp: false };
  }
  return {
    src: cardWebpUrl(cardId, hash, "full"),
    webp: true,
  };
}

/**
 * Href for `<link rel=preload as=image>`. Same URL the hero `<img>` requests
 * first, so the browser dedupes them. There is no preload onerror: a missing
 * object is one 404, then the img swaps to PNG. Preloading the PNG as well
 * would download the full PNG on every visit after the WebP exists.
 */
export function heroPreloadHref(cardId: string): string {
  return heroCardImageAttrs(cardId)?.src ?? "";
}

const prefetchedHeroUrls = new Set<string>();

let shownHero: ListCardImage | null = null;

/** Last hero that actually decoded. A variant navigation remounts the img, so this is what stays on screen. */
export function rememberShownHero(image: ListCardImage): void {
  if (!image.src) return;
  shownHero = image;
}

export function previousHeroImage(nextSrc: string): ListCardImage | null {
  if (!shownHero || !nextSrc || shownHero.src === nextSrc) return null;
  return shownHero;
}

export function clearShownHero(): void {
  shownHero = null;
}

/** Warm the full-size hero URL (WebP, or PNG after a remembered miss). Deduped per session. */
export function prefetchHeroImage(cardId: string): void {
  if (typeof window === "undefined") return;
  const href = heroPreloadHref(cardId);
  if (!href || prefetchedHeroUrls.has(href)) return;
  prefetchedHeroUrls.add(href);
  const img = new Image();
  img.decoding = "async";
  img.src = href;
}
