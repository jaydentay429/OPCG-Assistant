import { cardImagePacksUrl, cardImageProxyUrl, cardImageUrl } from "./api";

type Lang = "zh-Hant" | "zh-Hans" | "en";

export type ExportCardImagePlan = {
  /** `cardImageUrl(id)`, or "" when the manifest has no file. */
  cdn: string;
  /**
   * Current API art URLs (packs, then the image proxy).
   * Empty when `cdn` is empty: canvas export draws the gray placeholder
   * and does not request packs or the proxy.
   */
  api: string[];
};

/**
 * Canvas export tries the same CDN URL as the page, then the API.
 * The CDN often has no Access-Control-Allow-Origin, so a failed
 * crossOrigin load falls back to `api`. An empty manifest entry skips both.
 */
export function exportCardImagePlan(cardId: string): ExportCardImagePlan {
  const cdn = cardImageUrl(cardId);
  if (!cdn) return { cdn: "", api: [] };
  return {
    cdn,
    api: [cardImagePacksUrl(cardId), cardImageProxyUrl(cardId)],
  };
}

/** Same label as the on-page gray placeholder (`card.no_image`). */
export function cardImagePlaceholderLabel(lang: Lang): string {
  if (lang === "en") return "No image";
  if (lang === "zh-Hans") return "暂无图片";
  return "暫無圖片";
}

export const EXPORT_PLACEHOLDER_BG = "#4a5160";
export const EXPORT_PLACEHOLDER_FG = "#e8eaef";

/**
 * Load a CDN card image for canvas drawing.
 * `crossOrigin = "anonymous"` matches an `<img crossorigin>` fetch.
 * CORS failure, 404, and decode failure all resolve to null so the caller
 * can fall back to the API URLs.
 */
export function loadCdnCardImage(url: string): Promise<HTMLImageElement | null> {
  if (!url || typeof Image === "undefined") return Promise.resolve(null);
  return new Promise((resolve) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.decoding = "async";
    img.onload = () => resolve(img.naturalWidth > 0 ? img : null);
    img.onerror = () => resolve(null);
    img.src = url;
  });
}
