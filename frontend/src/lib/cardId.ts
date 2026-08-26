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
  // Strip parallel / alternate suffixes like -P1, -SP, -AA
  const m = id.match(/^([A-Z]{2,4}\d{0,2}-\d{3})/);
  return m ? m[1] : id;
}

/** UI label: show base id only (no -P1 / -R1 suffix). DON keeps full 5-digit id. */
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
