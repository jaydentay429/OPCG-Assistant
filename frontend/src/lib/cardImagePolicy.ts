import { hasCardImage } from "./api";

/**
 * True when this catalog id has no file in the card-image manifest.
 * The manifest is the only signal; card payload image fields are ignored.
 */
export function isSuppressedCardImage(cardId: string): boolean {
  const id = String(cardId || "").trim();
  if (!id) return false;
  return !hasCardImage(id);
}
