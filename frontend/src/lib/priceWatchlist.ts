import { normalizeCardId } from "@/lib/cardId";

const KEY = "opcg_price_watchlist_v1";
export const WATCHLIST_MAX = 80;

export function loadWatchlist(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    const out: string[] = [];
    const seen = new Set<string>();
    for (const item of parsed) {
      const id = normalizeCardId(String(item || ""));
      if (!id || seen.has(id)) continue;
      seen.add(id);
      out.push(id);
      if (out.length >= WATCHLIST_MAX) break;
    }
    return out;
  } catch {
    return [];
  }
}

function persist(ids: string[]) {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(ids.slice(0, WATCHLIST_MAX)));
  } catch {
    /* ignore */
  }
}

export function addToWatchlist(cardId: string): string[] {
  const id = normalizeCardId(cardId);
  if (!id) return loadWatchlist();
  const cur = loadWatchlist().filter((x) => x !== id);
  const next = [id, ...cur].slice(0, WATCHLIST_MAX);
  persist(next);
  return next;
}

export function removeFromWatchlist(cardId: string): string[] {
  const id = normalizeCardId(cardId);
  const next = loadWatchlist().filter((x) => x !== id);
  persist(next);
  return next;
}

export function clearWatchlist(): string[] {
  persist([]);
  return [];
}

export function isOnWatchlist(cardId: string, list?: string[]): boolean {
  const id = normalizeCardId(cardId);
  if (!id) return false;
  const src = list ?? loadWatchlist();
  return src.includes(id);
}
