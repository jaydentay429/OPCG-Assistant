import { displayCardId } from "./cardId";

/**
 * Separators people type between a set code and a collector number:
 * ASCII hyphen, underscore, space, fullwidth hyphen, and common dashes.
 */
const ID_SEPARATOR = /[-_＿\s.．·・/／\\－—–−‐‑‒]/g;

function foldAscii(text: string): string {
  return String(text || "").replace(/[\uFF01-\uFF5E]/g, (ch) =>
    String.fromCharCode(ch.charCodeAt(0) - 0xfee0),
  );
}

function compactId(text: string): string {
  return foldAscii(text).toLowerCase().replace(ID_SEPARATOR, "");
}

function catalogId(cardId: string): string {
  return foldAscii(String(cardId || ""))
    .trim()
    .toUpperCase()
    .replace(/_/g, "-")
    .replace(/\s+/g, "");
}

/** Complete catalog id, including compact `p160` / `op18076`. Not `CP9`, `Don`, or `OP18`. */
function canonicalFullCardId(query: string): string | null {
  const compact = compactId(query).toUpperCase();
  if (!compact || /[^A-Z0-9]/.test(compact)) return null;
  const promo = compact.match(/^P(\d{3,})([A-Z]\d+)?$/);
  if (promo) {
    const base = `P-${promo[1]}`;
    return promo[2] ? `${base}-${promo[2]}` : base;
  }
  const don = compact.match(/^(DON(?:EB|PRB)?)(\d{2})(\d{3,})([A-Z]\d+)?$/);
  if (don) {
    const base = `${don[1]}${don[2]}-${don[3]}`;
    return don[4] ? `${base}-${don[4]}` : base;
  }
  const numbered = compact.match(/^([A-Z]{2,4})(\d{2})(\d{3,})([A-Z]\d+)?$/);
  if (numbered && !numbered[1].startsWith("DON")) {
    const base = `${numbered[1]}${numbered[2]}-${numbered[3]}`;
    return numbered[4] ? `${base}-${numbered[4]}` : base;
  }
  return null;
}

/** Set-code prefix. Bare `DON` covers `DONPRB` and `DONEB`. */
function setPrefixMatches(cardId: string, query: string): boolean {
  if (canonicalFullCardId(query)) return false;
  const compact = compactId(query).toUpperCase();
  if (!compact || /[^A-Z0-9]/.test(compact)) return false;
  const cid = catalogId(cardId);
  if (!cid) return false;
  if (/^DON(?:EB|PRB)?\d{0,2}$/.test(compact)) {
    if (compact === "DON") return cid.startsWith("DON");
    return cid.startsWith(compact);
  }
  const numbered = compact.match(/^(OP|ST|EB|PRB)(\d{2})(\d{0,2})$/);
  if (!numbered) return false;
  const prefix = `${numbered[1]}${numbered[2]}`;
  const extra = numbered[3] || "";
  if (extra) return cid.startsWith(`${prefix}-${extra}`);
  return cid.startsWith(`${prefix}-`);
}

/**
 * Card-number match: exact id, parallel suffix, or a real set-code prefix.
 * Compact form is allowed (`OP18076`, `p160`) but never as a substring,
 * so `P160` does not match `OP16-001`. `Don` matches every DON-family id,
 * including `DONPRB` and `DONEB`. Letter-digit names (`CP9`, `Mr.1`) are not
 * card numbers. A digits-only query matches that collector-number segment.
 */
export function matchesCardId(cardId: string, query: string): boolean {
  const q = foldAscii(String(query || "")).trim().toLowerCase();
  if (!q) return true;
  const compact = compactId(q);
  if (!compact || !/^[a-z0-9]+$/.test(compact)) return false;

  const cidRaw = foldAscii(String(cardId || ""));
  const cidLower = cidRaw.toLowerCase().replace(/_/g, "-");
  const display = foldAscii(displayCardId(cidRaw)).toLowerCase();
  const cidCompact = compactId(cidLower);
  const displayCompact = compactId(display);

  if (/^\d+$/.test(compact)) {
    const groups = `${cidLower} ${display}`.match(/\d+/g) || [];
    return groups.some((group) => group === compact);
  }

  if (compact === cidCompact || compact === displayCompact) return true;

  const full = canonicalFullCardId(q);
  if (full) {
    const cid = catalogId(cardId);
    return cid === full || cid.startsWith(`${full}-`);
  }
  return setPrefixMatches(cardId, q);
}

/**
 * True when the query can be decided from the card id alone.
 * Ordinary words (`Don`, `CP9`, `Mr.1`, `GERMA 66`) stay false so name and
 * trait matches are not hidden before deck-stats metadata loads. A full card
 * id, a collector number, or a set code such as `OP18` / `ST01` stays true.
 * Bare `DON` is a word; `DONPRB` and `DONEB` are still set prefixes.
 */
export function queryLooksLikeCardNumber(query: string): boolean {
  const compact = compactId(String(query || "").trim());
  if (!compact || !/^[a-z0-9]+$/.test(compact)) return false;
  if (/^\d+$/.test(compact)) return true;
  if (canonicalFullCardId(query)) return true;
  const upper = compact.toUpperCase();
  if (/^DON(?:EB|PRB)?\d{0,2}$/.test(upper)) return upper !== "DON";
  if (/^(?:OP|ST|EB|PRB|P)$/.test(upper)) return true;
  return /^(?:OP|ST|EB|PRB)\d{2}\d{0,2}$/.test(upper);
}

export type BinderLibraryMeta = {
  searchBlob?: string | null;
};

/**
 * Whether one collection card stays in the binder library for `query`.
 *
 * Card numbers live on the collection key, so they filter even when deck-stats
 * metadata has not loaded. Name/trait search uses `matchName` only after that
 * metadata exists; until then those cards stay visible.
 */
export function binderLibraryCardMatches(
  cardId: string,
  query: string,
  metaLoaded: boolean,
  searchBlob: string | null | undefined,
  matchName: (cardId: string, searchBlob: string | null | undefined, query: string) => boolean,
): boolean {
  const q = String(query || "").trim();
  if (!q) return true;
  if (matchesCardId(cardId, q)) return true;
  if (!metaLoaded) return !queryLooksLikeCardNumber(q);
  return matchName(cardId, searchBlob, q);
}

export function filterBinderLibrary<T extends readonly [string, ...unknown[]]>(
  entries: readonly T[],
  query: string,
  metaById: Readonly<Record<string, BinderLibraryMeta | undefined>>,
  matchName: (cardId: string, searchBlob: string | null | undefined, query: string) => boolean = () => false,
): T[] {
  const q = String(query || "").trim();
  if (!q) return entries.slice();
  return entries.filter(([id]) =>
    binderLibraryCardMatches(
      id,
      q,
      Object.prototype.hasOwnProperty.call(metaById, id),
      metaById[id]?.searchBlob,
      matchName,
    ),
  );
}
