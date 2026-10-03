import type { FilterCard } from "@/lib/types";

export type SearchResultSnapshot = {
  key: string;
  cards: FilterCard[];
  total: number;
};

const memoryByScope = new Map<string, SearchResultSnapshot>();

function storageKeyForScope(scope: string): string {
  return scope.endsWith("embed") ? "opcg_embed_search_results_v1" : "opcg_search_results_v1";
}

function browserStorage(): Storage | null {
  try {
    if (typeof sessionStorage === "undefined") return null;
    return sessionStorage;
  } catch {
    return null;
  }
}

export function searchResultsCacheKey(
  scope: string,
  query: Record<string, string | number | undefined | null>,
): string {
  const parts = Object.keys(query)
    .sort()
    .map((name) => `${name}=${query[name] ?? ""}`);
  return `${scope}\n${parts.join("&")}`;
}

function isCardList(value: unknown): value is FilterCard[] {
  return Array.isArray(value) && value.every((row) => row && typeof row === "object" && typeof (row as FilterCard).id === "string");
}

export function rememberSearchResults(scope: string, snapshot: SearchResultSnapshot): void {
  memoryByScope.set(scope, snapshot);
  const store = browserStorage();
  if (!store) return;
  try {
    store.setItem(storageKeyForScope(scope), JSON.stringify(snapshot));
  } catch {
    /* quota or private mode: the in-memory copy still covers back navigation */
  }
}

export function recallSearchResults(scope: string, key: string): SearchResultSnapshot | null {
  const mem = memoryByScope.get(scope);
  if (mem && mem.key === key && isCardList(mem.cards)) return mem;
  const store = browserStorage();
  if (!store) return null;
  try {
    const raw = store.getItem(storageKeyForScope(scope));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<SearchResultSnapshot>;
    if (parsed.key !== key || !isCardList(parsed.cards)) return null;
    const snapshot = {
      key: parsed.key,
      cards: parsed.cards,
      total: Number.isFinite(Number(parsed.total)) ? Number(parsed.total) : parsed.cards.length,
    };
    memoryByScope.set(scope, snapshot);
    return snapshot;
  } catch {
    return null;
  }
}

/** Test hook. Production code does not need to clear this. */
export function clearSearchResultMemory(): void {
  memoryByScope.clear();
}
