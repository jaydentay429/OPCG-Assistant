export function normalizeCardId(raw: string): string {
  return String(raw || "")
    .trim()
    .toUpperCase()
    .replace(/_/g, "-");
}

export function isDonCardId(cardId: string): boolean {
  return /^DON[A-Z0-9]*-\d{3,5}(?:-[A-Z0-9]+)?$/i.test(normalizeCardId(cardId));
}

export function toBaseCardId(cardId: string): string {
  const id = normalizeCardId(cardId);
  // Illustrated DON cards use 3–5 digit tails (DON17-10163); do not truncate to 3 digits.
  const don = id.match(/^(DON[A-Z0-9]*-\d{3,5})(?:-[A-Z0-9]+)?$/);
  if (don) return don[1];
  // Promo P-084 / P-084-P1: series letter is a single P.
  const promo = id.match(/^(P-\d{3})(?:-[A-Z0-9]+)?$/);
  if (promo) return promo[1];
  // Strip parallel / alternate suffixes like -P1, -SP, -AA
  const m = id.match(/^([A-Z]{2,4}\d{0,2}-\d{3})/);
  return m ? m[1] : id;
}

/** Set / pack code from a catalog id (OP18-001-P1 → OP18, P-082 → P). */
export function setCodeFromCardId(cardId: string): string | null {
  const id = normalizeCardId(cardId);
  if (!id) return null;
  if (id.startsWith("DON")) return "DON";
  if (/^P-\d{3}/.test(id)) return "P";
  const m = id.match(/^([A-Z]{2,4}\d{0,2})-\d{3}/);
  return m ? m[1] : null;
}
export function displayCardId(cardId: string): string {
  return toBaseCardId(cardId);
}

export function cardIdSortKey(cardId: string): string {
  const id = normalizeCardId(cardId);
  const m = id.match(/^([A-Z]+)(\d*)-(\d+)(.*)$/);
  if (!m) return id;
  const series = m[1];
  const num = (m[2] || "0").padStart(3, "0");
  const code = m[3].padStart(5, "0");
  return `${series}${num}-${code}${m[4] || ""}`;
}
