import manifest from "../generated/card-image-manifest.json" with { type: "json" };
import { normalizeCardId } from "./cardId";

/** Catalog id → first 8 hex chars of the file's MD5. Generated; do not edit. */
export const CARD_IMAGE_MANIFEST: Readonly<Record<string, string>> = manifest;

/** Content hash for this id, or "" when the manifest has no file. */
export function cardImageHash(cardId: string): string {
  const id = normalizeCardId(cardId);
  if (!id) return "";
  const hash = CARD_IMAGE_MANIFEST[id];
  return typeof hash === "string" && /^[0-9a-f]{8}$/.test(hash) ? hash : "";
}
