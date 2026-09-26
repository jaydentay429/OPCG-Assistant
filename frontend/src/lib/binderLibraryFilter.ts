import { displayCardId } from "./cardId";

/**
 * Separators people type between a set code and a collector number:
 * ASCII hyphen, underscore, space, fullwidth hyphen, and common dashes.
 */
const ID_SEPARATOR = /[-_＿\s.．·・/／\\－—–−‐‑‒]/g;

/** Set codes with no digits yet (partial card numbers such as "ST" or "OP"). */
const SET_PREFIX = /^(?:op|st|eb|prb|don|p)$/;

function foldAscii(text: string): string {
  return String(text || "").replace(/[\uFF01-\uFF5E]/g, (ch) =>
    String.fromCharCode(ch.charCodeAt(0) - 0xfee0),
  );
}

function compactId(text: string): string {
  return foldAscii(text).toLowerCase().replace(ID_SEPARATOR, "");
}

/**
 * Card-number match: full or partial, case-insensitive, and tolerant of
 * separators users naturally type (`OP01-001`, `op01001`, `OP01 001`, `ST-01-001`).
 */
export function matchesCardId(cardId: string, query: string): boolean {
  const q = foldAscii(String(query || "")).trim().toLowerCase();
  if (!q) return true;
  const cidRaw = foldAscii(String(cardId || ""));
  const cidLower = cidRaw.toLowerCase().replace(/_/g, "-");
  const display = foldAscii(displayCardId(cidRaw)).toLowerCase();
  const qHyphen = q.replace(ID_SEPARATOR, "-").replace(/-+/g, "-");
  const qCompact = compactId(q);
  const cidCompact = compactId(cidLower);
  const displayCompact = compactId(display);
  if (display.includes(q) || cidLower.includes(q)) return true;
  if (qHyphen && (display.includes(qHyphen) || cidLower.includes(qHyphen))) return true;
  if (qCompact && (cidCompact.includes(qCompact) || displayCompact.includes(qCompact))) return true;
  return false;
}

/**
 * True when the query can be decided from the card id alone.
 * Name and trait queries (no digits, not a set prefix) stay false so they can
 * wait for deck-stats metadata instead of flashing an empty list.
 */
export function queryLooksLikeCardNumber(query: string): boolean {
  const compact = compactId(String(query || "").trim());
  if (!compact || !/^[a-z0-9]+$/.test(compact)) return false;
  if (/\d/.test(compact)) return true;
  return SET_PREFIX.test(compact);
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
