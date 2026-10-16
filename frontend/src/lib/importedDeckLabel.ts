import { displayCardId } from "./cardId";

/** English sentinel stored when a pasted list has no deck name. */
export const IMPORTED_DECK_SENTINEL = "Imported";

export function importedDeckName(
  name: string | null | undefined,
  t: (key: string) => string,
): string {
  const raw = String(name || "").trim();
  if (!raw || raw === IMPORTED_DECK_SENTINEL) return t("play.imported_ok");
  return raw;
}

export function importedDeckOptionLabel(
  name: string | null | undefined,
  leaderId: string,
  t: (key: string) => string,
): string {
  return `${importedDeckName(name, t)} · ${displayCardId(leaderId)} · 50/50`;
}
