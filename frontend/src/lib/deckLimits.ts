import { normalizeCardId, toBaseCardId } from "@/lib/cardId";

/** Official "any number in deck" characters (base IDs). Variants like -P1 inherit this. */
const UNLIMITED_COPY_BASES = new Set(["OP01-075", "OP08-072", "OP16-042"]);

/** Max copies of one card id allowed in the 50-card main deck. */
export function maxCopiesForCard(cardId: string): number {
  const id = normalizeCardId(cardId);
  if (!id) return 4;
  const base = toBaseCardId(id);
  if (UNLIMITED_COPY_BASES.has(base) || UNLIMITED_COPY_BASES.has(id)) return 50;
  return 4;
}

export function clampDeckCopies(cardId: string, qty: number): number {
  const n = Math.floor(Number(qty) || 0);
  if (n <= 0) return 0;
  return Math.min(maxCopiesForCard(cardId), n);
}
