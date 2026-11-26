import type { PriceHistoryPoint } from "./types";

/**
 * Price history only stores a point when the price changes. A card whose price
 * has not moved since July therefore has one point even if it was re-checked
 * yesterday. The chart extends the line to the last time the price was seen,
 * so an unchanged price reads as a flat line up to that date instead of
 * "only one sync".
 */
export function chartHistory(
  history: PriceHistoryPoint[] | null | undefined,
  currentPrice: number | null | undefined,
  lastSeen: string | null | undefined,
): PriceHistoryPoint[] {
  const rows = Array.isArray(history) ? history.filter((row) => row && row.ts) : [];
  if (!rows.length || currentPrice == null || !lastSeen) return rows;
  const last = rows[rows.length - 1];
  const lastTs = Date.parse(String(last.ts));
  const seenTs = Date.parse(String(lastSeen));
  if (!Number.isFinite(lastTs) || !Number.isFinite(seenTs)) return rows;
  // Same day or earlier adds nothing.
  if (seenTs - lastTs < 24 * 3600 * 1000) return rows;
  if (Number(last.price) !== Number(currentPrice)) return rows;
  return [...rows, { ts: String(lastSeen), price: Number(currentPrice) }];
}

/** Whole days between `iso` and `now` (null when unparsable). */
export function daysSince(iso: string | null | undefined, now = Date.now()): number | null {
  const ts = Date.parse(String(iso || ""));
  if (!Number.isFinite(ts)) return null;
  return Math.max(0, Math.floor((now - ts) / (24 * 3600 * 1000)));
}
