import { normalizeCardId } from "@/lib/cardId";
import type { FilterState } from "@/lib/types";

const KEY = "opcg_prices_prefs_v1";

export type PricesTab = "assets" | "calc" | "market" | "watch";
export type MarketSort = "id" | "price_desc" | "price_asc";

const TABS: PricesTab[] = ["assets", "calc", "market", "watch"];
const SORTS: MarketSort[] = ["id", "price_desc", "price_asc"];
const FILTER_KEYS: (keyof FilterState)[] = [
  "colors",
  "costs",
  "counters",
  "powers",
  "card_types",
  "attributes",
  "keywords",
  "serieses",
  "rarities",
  "blocks",
];

export const EMPTY_FILTER_STATE: FilterState = {
  colors: [],
  costs: [],
  counters: [],
  powers: [],
  card_types: [],
  attributes: [],
  keywords: [],
  serieses: [],
  rarities: [],
  blocks: [],
};

export type MarketPrefs = {
  q: string;
  filters: FilterState;
  sort: MarketSort;
  priceMin: string;
  priceMax: string;
  page: number;
  scrollY: number;
  scrollAnchor: string;
};

export type CalcPrefs = {
  text: string;
  leader: string | null;
  cards: Record<string, number>;
};

export type AssetsPrefs = {
  showTop: boolean;
  openDeckId: string | null;
};

type PricesPrefs = {
  tab?: PricesTab;
  market?: Partial<MarketPrefs>;
  calc?: Partial<CalcPrefs>;
  assets?: Partial<AssetsPrefs>;
};

function readAll(): PricesPrefs {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as unknown;
    return parsed && typeof parsed === "object" ? (parsed as PricesPrefs) : {};
  } catch {
    return {};
  }
}

function writeAll(next: PricesPrefs) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    /* ignore storage failures */
  }
}

export function readTabPref(): PricesTab | null {
  const saved = readAll().tab;
  return TABS.includes(saved as PricesTab) ? (saved as PricesTab) : null;
}

export function saveTabPref(tab: PricesTab) {
  writeAll({ ...readAll(), tab });
}

function sanitizeFilters(raw: unknown): FilterState {
  const out: FilterState = { ...EMPTY_FILTER_STATE };
  if (!raw || typeof raw !== "object") return out;
  const src = raw as Record<string, unknown>;
  for (const key of FILTER_KEYS) {
    const list = src[key];
    if (!Array.isArray(list)) continue;
    out[key] = list.filter((x): x is string => typeof x === "string");
  }
  return out;
}

function toStr(raw: unknown, fallback = ""): string {
  return typeof raw === "string" ? raw : fallback;
}

export function readMarketPrefs(): MarketPrefs {
  const saved = readAll().market || {};
  const page = Number(saved.page);
  const scrollY = Number(saved.scrollY);
  return {
    q: toStr(saved.q),
    filters: sanitizeFilters(saved.filters),
    sort: SORTS.includes(saved.sort as MarketSort) ? (saved.sort as MarketSort) : "id",
    priceMin: toStr(saved.priceMin),
    priceMax: toStr(saved.priceMax),
    page: Number.isFinite(page) && page >= 1 ? Math.floor(page) : 1,
    scrollY: Number.isFinite(scrollY) && scrollY > 0 ? Math.floor(scrollY) : 0,
    scrollAnchor: toStr(saved.scrollAnchor),
  };
}

export function saveMarketPrefs(prefs: MarketPrefs) {
  writeAll({ ...readAll(), market: prefs });
}

export function readCalcPrefs(): CalcPrefs {
  const saved = readAll().calc || {};
  const cards: Record<string, number> = {};
  if (saved.cards && typeof saved.cards === "object") {
    for (const [rawId, rawQty] of Object.entries(saved.cards)) {
      const id = normalizeCardId(String(rawId));
      const qty = Math.floor(Number(rawQty) || 0);
      if (id && qty > 0) cards[id] = qty;
    }
  }
  const leader = saved.leader ? normalizeCardId(String(saved.leader)) || null : null;
  return { text: toStr(saved.text), leader, cards };
}

export function saveCalcPrefs(prefs: CalcPrefs) {
  writeAll({ ...readAll(), calc: prefs });
}

export function readAssetsPrefs(): AssetsPrefs {
  const saved = readAll().assets || {};
  return {
    showTop: saved.showTop === true,
    openDeckId: typeof saved.openDeckId === "string" ? saved.openDeckId : null,
  };
}

export function saveAssetsPrefs(prefs: AssetsPrefs) {
  writeAll({ ...readAll(), assets: prefs });
}
