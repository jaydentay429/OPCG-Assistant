import { SUPPRESSED_CARD_IMAGE_IDS } from "./suppressedCardImages.generated";

const SUPPRESSED = new Set(SUPPRESSED_CARD_IMAGE_IDS.map((id) => id.toUpperCase()));

/** Packs/CDN file for this id is a known mismatch and must not be shown. */
export function isSuppressedCardImage(cardId: string): boolean {
  const id = String(cardId || "").trim().toUpperCase();
  return Boolean(id) && SUPPRESSED.has(id);
}
