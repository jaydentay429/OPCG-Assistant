import { fetchPricesBatch, type BatchPriceFields } from "@/lib/api";

export type QtyMap = Record<string, number>;

/** Fetch unit prices for many ids, chunked to the API's batch limit. */
export async function loadUnitPrices(ids: string[]): Promise<Record<string, BatchPriceFields>> {
  const unique = [...new Set(ids.map((x) => String(x || "").trim()).filter(Boolean))];
  if (!unique.length) return {};
  const out: Record<string, BatchPriceFields> = {};
  const chunkSize = 400;
  for (let i = 0; i < unique.length; i += chunkSize) {
    const chunk = unique.slice(i, i + chunkSize);
    const part = await fetchPricesBatch(chunk);
    Object.assign(out, part);
  }
  return out;
}

export function unitPriceOf(
  prices: Record<string, BatchPriceFields>,
  cardId: string,
): number | null {
  const raw = prices[cardId]?.current_price;
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? n : null;
}

/** Sum qty × unit price. Missing prices are skipped (not counted as 0). */
export function sumPricedCopies(
  cards: QtyMap,
  prices: Record<string, BatchPriceFields>,
): { total: number; pricedCopies: number; missingCopies: number } {
  let total = 0;
  let pricedCopies = 0;
  let missingCopies = 0;
  for (const [id, rawQty] of Object.entries(cards)) {
    const qty = Math.max(0, Math.floor(Number(rawQty) || 0));
    if (!qty) continue;
    const unit = unitPriceOf(prices, id);
    if (unit == null) {
      missingCopies += qty;
      continue;
    }
    total += unit * qty;
    pricedCopies += qty;
  }
  return { total, pricedCopies, missingCopies };
}

export function formatYen(price: number | null | undefined): string {
  if (price == null || !Number.isFinite(Number(price))) return "—";
  return `¥${Number(price).toLocaleString("ja-JP")}`;
}
