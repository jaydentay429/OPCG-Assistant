import { API_BASE, type TopdeckBrief } from "./api";
import { normalizeCardId, toBaseCardId } from "./cardId";

/** Leaders with fewer decks than this render but are noindex and stay out of the sitemap. */
export const LEADER_INDEX_MIN_DECKS = 5;

export type LeaderSummary = {
  leader: string;
  name: string;
  name_hans: string;
  name_en: string;
  colors_en?: string[];
  decks: number;
  wins: number;
  top_finishes: number;
  formats: Record<string, number>;
  first_date: string;
  last_date: string;
};

export type LeaderCommonCard = {
  id: string;
  name: string;
  name_hans: string;
  name_en: string;
  card_type_en?: string;
  decks: number;
  rate: number;
  avg_qty: number;
};

export type LeaderDetail = LeaderSummary & {
  sample_decks: number;
  common_cards: LeaderCommonCard[];
  champion_decks: TopdeckBrief[];
  recent_decks: TopdeckBrief[];
  synced_at?: string | null;
};

export type LeaderList = {
  synced_at?: string | null;
  total_decks: number;
  items: LeaderSummary[];
};

const LEADER_REVALIDATE_SECONDS = 1800;

async function getJson<T>(path: string, timeoutMs = 8000): Promise<T | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      signal: controller.signal,
      next: { revalidate: LEADER_REVALIDATE_SECONDS },
    });
    if (res.status === 404) return null;
    if (!res.ok) throw new Error(`HTTP ${res.status} ${path}`);
    return (await res.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

export async function fetchLeaders(minDecks = 1): Promise<LeaderList | null> {
  return getJson<LeaderList>(`/topdecks/leaders?min_decks=${Math.max(1, Math.floor(minDecks))}`);
}

/** `null` means the API has no decks for this leader (404). Network errors throw. */
export async function fetchLeader(leaderId: string): Promise<LeaderDetail | null> {
  const id = toBaseCardId(normalizeCardId(leaderId));
  if (!id) return null;
  return getJson<LeaderDetail>(`/topdecks/leaders/${encodeURIComponent(id)}`);
}

export function leaderDisplayName(
  row: { name?: string; name_hans?: string; name_en?: string; leader?: string; id?: string },
  lang: string,
): string {
  const id = row.leader || row.id || "";
  if (lang === "en") return row.name_en || row.name || id;
  if (lang === "zh-Hans") return row.name_hans || row.name || row.name_en || id;
  return row.name || row.name_en || id;
}

export function leaderIsIndexable(row: { decks: number } | null | undefined): boolean {
  return !!row && row.decks >= LEADER_INDEX_MIN_DECKS;
}

/** "2026-11-20" → "20/11/2026" (zh-Hant), "2026/11/20" (zh-Hans), "11/20/2026" (en). */
export function formatLeaderDate(iso: string, lang: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso || ""));
  if (!m) return iso || "";
  const [, y, mo, d] = m;
  if (lang === "en") return `${mo}/${d}/${y}`;
  if (lang === "zh-Hans") return `${y}/${mo}/${d}`;
  return `${d}/${mo}/${y}`;
}

/** Deck date "11/20/2026" (source M/D/YYYY) → ISO, or "" when unparsable. */
export function topdeckDateIso(raw: string | null | undefined): string {
  const m = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(String(raw || "").trim());
  if (!m) return "";
  return `${m[3]}-${m[1].padStart(2, "0")}-${m[2].padStart(2, "0")}`;
}
