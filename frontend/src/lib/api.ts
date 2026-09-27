import type {
  BinderResponse,
  BinderShareCreateResponse,
  BinderSharedResponse,
  Card,
  CardDetailResponse,
  CardPriceResponse,
  CollectionResponse,
  CommunityCategory,
  CommunityPost,
  CommunityReport,
  CommunityTag,
  CommunityThread,
  CommunityThreadListResult,
  Deck,
  DeckListResponse,
  FilterCard,
  FilterOptions,
  LoginResponse,
  MeResponse,
  PhotoRecognizeResponse,
} from "./types";

export const API_BASE = (() => {
  const fromEnv =
    (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "")) || "";
  // Browser on local preview must hit local API (never production).
  if (typeof window !== "undefined") {
    const host = window.location.hostname;
    if (host === "localhost" || host === "127.0.0.1") {
      return fromEnv && /127\.0\.0\.1|localhost/i.test(fromEnv)
        ? fromEnv
        : "http://127.0.0.1:8000";
    }
    if (host === "optcgassistant.com" || host === "www.optcgassistant.com") {
      return "https://api.optcgassistant.com";
    }
  }
  if (fromEnv) return fromEnv;
  return "http://127.0.0.1:8000";
})();

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : `HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

const DEFAULT_GET_TIMEOUT_MS = 15000;

function authHeaders(token?: string | null): Record<string, string> {
  const h: Record<string, string> = { Accept: "application/json" };
  if (token) h.Authorization = `Bearer ${token}`;
  return h;
}

function formatDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((x) => (typeof x === "object" && x && "msg" in x ? String((x as { msg: unknown }).msg) : JSON.stringify(x)))
      .join("; ");
  }
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  return String(detail ?? "error");
}

async function parseError(res: Response): Promise<never> {
  let detail: unknown = res.statusText;
  try {
    const j = await res.json();
    detail = j.detail ?? j.error ?? j.message ?? j;
  } catch {
    /* ignore */
  }
  throw new ApiError(res.status, formatDetail(detail));
}

export async function apiGet<T>(
  path: string,
  opts?: {
    token?: string | null;
    query?: Record<string, string | number | undefined | null>;
    timeoutMs?: number;
    /** Default no-store; use "default" for short-lived catalog caches (search/filters). */
    cache?: RequestCache;
    signal?: AbortSignal;
  },
): Promise<{ data: T; headers: Headers }> {
  const url = new URL(path.startsWith("http") ? path : `${API_BASE}${path}`);
  if (opts?.query) {
    for (const [k, v] of Object.entries(opts.query)) {
      if (v === undefined || v === null || v === "") continue;
      url.searchParams.set(k, String(v));
    }
  }
  const controller = new AbortController();
  const timeoutMs = Math.max(1000, opts?.timeoutMs ?? DEFAULT_GET_TIMEOUT_MS);
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const onOuterAbort = () => controller.abort();
  if (opts?.signal) {
    if (opts.signal.aborted) controller.abort();
    else opts.signal.addEventListener("abort", onOuterAbort, { once: true });
  }
  let res: Response;
  try {
    res = await fetch(url.toString(), {
      headers: authHeaders(opts?.token),
      cache: opts?.cache ?? "no-store",
      signal: controller.signal,
    });
  } catch (e) {
    if (typeof e === "object" && e && "name" in e && (e as { name?: string }).name === "AbortError") {
      throw new ApiError(408, `请求超时（>${Math.round(timeoutMs / 1000)}s），请重试`);
    }
    throw e;
  } finally {
    clearTimeout(timer);
    opts?.signal?.removeEventListener("abort", onOuterAbort);
  }
  if (!res.ok) await parseError(res);
  return { data: (await res.json()) as T, headers: res.headers };
}

export async function apiSend<T>(
  path: string,
  method: string,
  body?: unknown,
  token?: string | null,
  opts?: { timeoutMs?: number },
): Promise<T> {
  const headers: Record<string, string> = {
    ...authHeaders(token),
    "Content-Type": "application/json",
  };
  const controller = new AbortController();
  const timeoutMs = Math.max(1000, opts?.timeoutMs ?? 20000);
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
      signal: controller.signal,
    });
  } catch (e) {
    if (typeof e === "object" && e && "name" in e && (e as { name?: string }).name === "AbortError") {
      throw new ApiError(408, `请求超时（>${Math.round(timeoutMs / 1000)}s），请重试`);
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) await parseError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Bump when packs art language/source changes so browsers skip stale max-age caches. */
export const CARD_IMAGE_CACHE_BUST = "20260826op119v5";

/** Cloudflare R2 / img subdomain — keeps card art off the API origin. */
export const PACKS_CDN_BASE = (() => {
  const fromEnv =
    (typeof process !== "undefined" && process.env.NEXT_PUBLIC_PACKS_CDN_URL?.replace(/\/$/, "")) || "";
  if (fromEnv) return fromEnv;
  const siteUrl = (typeof process !== "undefined" && process.env.NEXT_PUBLIC_SITE_URL) || "";
  if (siteUrl.includes("optcgassistant.com")) return "https://img.optcgassistant.com";
  if (typeof window !== "undefined") {
    const host = window.location.hostname;
    if (host === "optcgassistant.com" || host === "www.optcgassistant.com") {
      return "https://img.optcgassistant.com";
    }
  }
  return "";
})();

function isBlockedCardImageUrl(url: string): boolean {
  const lower = url.toLowerCase();
  return (
    lower.includes("limitless") ||
    lower.includes("_en.") ||
    lower.includes("en.onepiece-cardgame")
  );
}

/** Ensure our CDN /packs image URLs always carry the bust query (API local URLs often omit it). */
function withCardImageCacheBust(url: string): string {
  const raw = String(url || "").trim();
  if (!raw) return raw;
  try {
    const u = new URL(raw, "https://optcgassistant.com");
    const host = u.hostname.toLowerCase();
    const path = u.pathname.toLowerCase();
    const isOurCdn = host === "img.optcgassistant.com";
    const isOurPacks =
      (host === "api.optcgassistant.com" || host === "127.0.0.1" || host === "localhost") &&
      path.includes("/packs/");
    if (!isOurCdn && !isOurPacks) return raw;
    u.searchParams.set("v", CARD_IMAGE_CACHE_BUST);
    return u.toString();
  } catch {
    return raw;
  }
}

export function cardImageUrl(cardId: string): string {
  return `${API_BASE}/images/card/${encodeURIComponent(cardId)}?v=${CARD_IMAGE_CACHE_BUST}`;
}

export function cardImagePacksUrl(cardId: string): string {
  return `${API_BASE}/packs/${encodeURIComponent(cardId)}.png?v=${CARD_IMAGE_CACHE_BUST}`;
}

export function cardImageCdnUrl(cardId: string): string | null {
  const id = String(cardId || "").trim();
  if (!id || !PACKS_CDN_BASE) return null;
  return `${PACKS_CDN_BASE}/${encodeURIComponent(id)}.png?v=${CARD_IMAGE_CACHE_BUST}`;
}

/** Preferred → fallback order for CardImg (CDN first, then API packs, then proxy). */
export function cardImageSources(cardId: string, localUrl?: string | null): string[] {
  const id = String(cardId || "").trim();
  if (!id) return [];
  const out: string[] = [];
  const push = (raw: string | null | undefined) => {
    const u = String(raw || "").trim();
    if (!u || isBlockedCardImageUrl(u) || out.includes(u)) return;
    out.push(u);
  };
  // Prefer versioned CDN over API's bare img_local_url (same host, no ?v= → stale browser cache).
  push(cardImageCdnUrl(id));
  push(withCardImageCacheBust(localUrl || ""));
  push(cardImagePacksUrl(id));
  push(cardImageUrl(id));
  return out;
}

const prefetchedImages = new Set<string>();

/** Warm browser cache for card faces (CDN first, API fallbacks). */
export function prefetchCardImages(cardIds: Iterable<string | null | undefined>): void {
  if (typeof window === "undefined") return;
  for (const raw of cardIds) {
    const id = String(raw || "").trim();
    if (!id || prefetchedImages.has(id)) continue;
    prefetchedImages.add(id);
    const chain = cardImageSources(id);
    if (!chain.length) continue;
    let step = 0;
    const img = new Image();
    img.decoding = "async";
    const tryNext = () => {
      if (step >= chain.length) return;
      img.src = chain[step];
    };
    img.onerror = () => {
      step += 1;
      tryNext();
    };
    tryNext();
  }
}

export async function fetchFilterOptions(): Promise<FilterOptions> {
  const { data } = await apiGet<FilterOptions>("/filters/options");
  return data;
}

export async function fetchFilterCards(
  query: Record<string, string | number | undefined | null>,
  opts?: { signal?: AbortSignal },
): Promise<{ cards: FilterCard[]; total: number }> {
  const { data, headers } = await apiGet<FilterCard[]>("/filters/cards", {
    query,
    cache: "default",
    signal: opts?.signal,
  });
  const total = Number(headers.get("X-Total-Count") || data.length);
  return { cards: data, total };
}

export async function fetchCard(cardId: string, includeAi = false): Promise<CardDetailResponse> {
  const { data } = await apiGet<CardDetailResponse>(`/cards/${encodeURIComponent(cardId)}`, {
    query: { include_ai: includeAi ? "1" : "0" },
  });
  return data;
}

const briefCardCache = new Map<string, Card>();

export async function fetchCardBrief(cardId: string): Promise<Card> {
  const id = String(cardId || "").trim();
  if (!id) throw new ApiError(422, "card_id required");
  const hit = briefCardCache.get(id);
  if (hit) return hit;
  const { data } = await apiGet<Card>(`/cards/${encodeURIComponent(id)}/brief`, {
    timeoutMs: 8000,
  });
  briefCardCache.set(id, data);
  return data;
}

export async function fetchCardPrice(cardId: string): Promise<CardPriceResponse> {
  const { data } = await apiGet<CardPriceResponse>(`/prices/${encodeURIComponent(cardId)}`, {
    query: { exact: "true" },
  });
  return data;
}

export type BatchPriceFields = {
  card_id?: string;
  source?: string;
  currency?: string;
  current_price?: number | null;
  last_seen?: string | null;
  last_checked?: string | null;
};

export async function fetchPricesBatch(ids: string[]): Promise<Record<string, BatchPriceFields>> {
  const unique = [...new Set(ids.map((x) => String(x || "").trim()).filter(Boolean))];
  if (!unique.length) return {};
  return apiSend<Record<string, BatchPriceFields>>("/prices/batch", "POST", { ids: unique });
}

export type PricesMetaResponse = {
  source?: string;
  currency?: string;
  updated_at?: string | null;
  priced_count?: number;
  total_entries?: number;
};

export async function fetchPricesMeta(): Promise<PricesMetaResponse> {
  const { data } = await apiGet<PricesMetaResponse>("/prices/meta");
  return data;
}

export type TopdeckMetaRow = {
  slug: string;
  title: string;
  url?: string;
  modified?: string;
  deck_count?: number;
};

export type TopdeckFacetRow = {
  value: string;
  count: number;
  label_en?: string;
  label_zh_Hans?: string;
  label_zh_Hant?: string;
};

export type TopdecksMetaResponse = {
  source?: string;
  attribution?: string;
  synced_at?: string;
  stats?: Record<string, unknown>;
  formats?: {
    jp?: { label?: string; metas?: TopdeckMetaRow[] };
    en?: { label?: string; metas?: TopdeckMetaRow[] };
  };
  facets?: {
    country?: TopdeckFacetRow[];
    host?: TopdeckFacetRow[];
    author?: TopdeckFacetRow[];
    tournament?: TopdeckFacetRow[];
    placement?: TopdeckFacetRow[];
    leader?: TopdeckFacetRow[];
  };
};

export type TopdeckBrief = {
  id: string;
  format?: string;
  meta_slug?: string;
  meta_title?: string;
  name?: string;
  author?: string;
  country?: string;
  country_key?: string;
  country_labels?: { en?: string; "zh-Hans"?: string; "zh-Hant"?: string };
  date?: string;
  placement?: string;
  placement_key?: string;
  placement_labels?: { en?: string; "zh-Hans"?: string; "zh-Hant"?: string };
  tournament?: string;
  tournament_key?: string;
  tournament_labels?: { en?: string; "zh-Hans"?: string; "zh-Hant"?: string };
  host?: string;
  host_key?: string;
  leader?: string;
  leader_name?: string;
  leader_name_en?: string;
  card_count?: number;
  source_url?: string;
  meta_url?: string;
  like_count?: number;
  liked_by_me?: boolean;
};

export type TopdeckDetail = TopdeckBrief & {
  cards?: Array<{
    id: string;
    qty: number;
    name?: string;
    name_en?: string;
    card_type?: string;
    is_leader?: boolean;
  }>;
};

export async function fetchTopdecksMeta(): Promise<TopdecksMetaResponse> {
  const { data } = await apiGet<TopdecksMetaResponse>("/topdecks/meta", { cache: "default" });
  return data;
}

export async function fetchTopdecksDecks(query: {
  format?: string;
  meta?: string;
  country?: string;
  host?: string;
  author?: string;
  tournament?: string;
  placement?: string;
  leader?: string;
  q?: string;
  offset?: number;
  limit?: number;
  token?: string | null;
}): Promise<{ total: number; offset: number; limit: number; items: TopdeckBrief[] }> {
  const { token, ...rest } = query;
  const { data } = await apiGet<{ total: number; offset: number; limit: number; items: TopdeckBrief[] }>(
    "/topdecks/decks",
    {
      query: rest,
      token,
      // Anonymous list is Cache-Control:public on API; avoid no-store remount tax.
      cache: token ? "no-store" : "default",
    },
  );
  return data;
}

export async function fetchTopdecksDetail(deckId: string, token?: string | null): Promise<TopdeckDetail> {
  const { data } = await apiGet<TopdeckDetail>(`/topdecks/decks/${encodeURIComponent(deckId)}`, { token });
  return data;
}

export async function likeTopdeck(
  token: string,
  deckId: string,
  liked: boolean,
): Promise<{ deck_id: string; like_count: number; liked_by_me: boolean }> {
  return apiSend("/topdecks/likes", "POST", { deck_id: deckId, liked }, token);
}

export type CardTournamentAppearance = TopdeckBrief & {
  qty?: number;
  is_leader?: boolean;
};

export async function fetchCardTournaments(
  cardId: string,
  limit = 10,
  opts?: { cache?: RequestCache },
): Promise<{ card_base_id: string; total_matched: number; items: CardTournamentAppearance[] }> {
  const { data } = await apiGet<{
    card_base_id: string;
    total_matched: number;
    items: CardTournamentAppearance[];
  }>(`/cards/${encodeURIComponent(cardId)}/tournaments`, {
    query: { limit },
    // Browser callers keep "default" (HTTP cache). Card-page SSR passes
    // "no-store" so a gateway 502 cannot sit in the Next fetch data cache.
    cache: opts?.cache ?? "default",
  });
  return data;
}

export type CardComment = {
  id: number;
  card_base_id: string;
  body: string;
  anonymous: boolean;
  author_username: string;
  is_self: boolean;
  like_count: number;
  liked_by_me: boolean;
  created_at: string;
  edited_at?: string | null;
};

export async function fetchCardComments(
  cardId: string,
  opts: { token?: string | null; offset?: number; limit?: number } = {},
): Promise<{ card_base_id: string; total: number; comments: CardComment[] }> {
  const { data } = await apiGet<{ card_base_id: string; total: number; comments: CardComment[] }>(
    `/cards/${encodeURIComponent(cardId)}/comments`,
    { token: opts.token, query: { offset: opts.offset ?? 0, limit: opts.limit ?? 40 } },
  );
  return data;
}

export async function createCardComment(
  token: string,
  cardId: string,
  body: { body: string; anonymous?: boolean },
): Promise<CardComment> {
  return apiSend<CardComment>(`/cards/${encodeURIComponent(cardId)}/comments`, "POST", body, token);
}

export async function likeCardComment(
  token: string,
  commentId: number,
  liked: boolean,
): Promise<{ comment_id: number; like_count: number; liked_by_me: boolean }> {
  return apiSend(`/cards/comments/${commentId}/like`, "POST", { liked }, token);
}

export async function reportCardComment(
  token: string,
  commentId: number,
  reason: string,
): Promise<{ ok: boolean; report_id: number }> {
  return apiSend(`/cards/comments/${commentId}/report`, "POST", { reason }, token);
}

export async function deleteCardComment(token: string, commentId: number): Promise<{ ok: boolean }> {
  return apiSend(`/cards/comments/${commentId}`, "DELETE", undefined, token);
}

export async function login(loginId: string, password: string): Promise<LoginResponse> {
  return apiSend<LoginResponse>("/auth/login", "POST", { login: loginId, password }, null, { timeoutMs: 12000 });
}

export async function register(email: string, username: string, password: string): Promise<unknown> {
  return apiSend("/auth/register", "POST", { email, username, password });
}

export async function forgotPassword(email: string): Promise<{ status?: string; message?: string }> {
  return apiSend<{ status?: string; message?: string }>("/auth/forgot-password", "POST", { email });
}

export async function resetPassword(
  token: string,
  password: string,
): Promise<{ status?: string; message?: string }> {
  return apiSend<{ status?: string; message?: string }>("/auth/reset-password", "POST", {
    token,
    password,
  });
}

export async function fetchMe(token: string): Promise<MeResponse> {
  const { data } = await apiGet<MeResponse>("/auth/me", { token });
  return data;
}

export async function fetchCollection(token: string): Promise<CollectionResponse> {
  const { data } = await apiGet<CollectionResponse>("/collection", { token });
  return data;
}

export async function collectionAdd(token: string, cardId: string, count = 1): Promise<CollectionResponse> {
  return apiSend<CollectionResponse>("/collection/cards", "POST", { card_id: cardId, count }, token);
}

export async function collectionRemove(
  token: string,
  cardId: string,
  count = 1,
): Promise<CollectionResponse> {
  const url = `/collection/cards/${encodeURIComponent(cardId)}?count=${count}`;
  return apiSend<CollectionResponse>(url, "DELETE", undefined, token);
}

export async function fetchDecks(token: string): Promise<DeckListResponse> {
  const { data } = await apiGet<DeckListResponse>("/decks", { token });
  return data;
}

export type BattleRoomPlayer = {
  user_id: string;
  username: string;
  is_ai: boolean;
  ready?: boolean;
  has_deck?: boolean;
  deck_id?: string | null;
  deck_name?: string | null;
  leader_card_id?: string | null;
};

export type BattleRoomInfo = {
  type?: string;
  room_code: string;
  vs_ai?: boolean;
  hotseat?: boolean;
  ranked?: boolean;
  status: string;
  allow_spectators?: boolean;
  spectator_show_hands?: boolean;
  can_spectate?: boolean;
  players?: Array<BattleRoomPlayer | null>;
  guest_token?: string | null;
  guest_user_id?: string | null;
  guest_username?: string | null;
};

export type BattleInlineDeck = {
  leader_card_id: string;
  cards: Record<string, number>;
  name?: string;
};

export type AiBattleDeck = {
  id: string;
  name: string;
  leader_card_id: string;
  non_leader_count: number;
  cards?: Record<string, number>;
};

export async function fetchBattleGuestToken(): Promise<{
  guest_token: string;
  guest_user_id: string;
  guest_username: string;
}> {
  return apiSend("/battle/guest-token", "POST", {});
}

export async function fetchAiBattleDecks(): Promise<AiBattleDeck[]> {
  const { data } = await apiGet<{ decks: AiBattleDeck[] }>("/battle/ai-decks");
  return data.decks || [];
}

export async function createBattleRoom(
  token: string | null | undefined,
  opts: {
    deckId?: string | null;
    deck?: BattleInlineDeck | null;
    vsAi?: boolean;
    aiDeckId?: string | null;
    hotseat?: boolean;
    oppDeckId?: string | null;
    oppDeck?: BattleInlineDeck | null;
    allowSpectators?: boolean;
    spectatorShowHands?: boolean;
  } = {},
): Promise<BattleRoomInfo> {
  const vsAi = Boolean(opts.vsAi);
  const hotseat = Boolean(opts.hotseat);
  return apiSend<BattleRoomInfo>(
    "/battle/rooms",
    "POST",
    {
      vs_ai: vsAi,
      hotseat,
      allow_spectators: opts.allowSpectators ?? true,
      spectator_show_hands: opts.spectatorShowHands ?? true,
      ...(opts.deckId ? { deck_id: opts.deckId } : {}),
      ...(opts.deck ? { deck: opts.deck } : {}),
      ...(vsAi && opts.aiDeckId ? { ai_deck_id: opts.aiDeckId } : {}),
      ...(hotseat && opts.oppDeckId ? { opp_deck_id: opts.oppDeckId } : {}),
      ...(hotseat && opts.oppDeck ? { opp_deck: opts.oppDeck } : {}),
    },
    token,
  );
}

export async function submitBattleBugReport(
  token: string,
  payload: {
    message: string;
    room_code?: string | null;
    phase?: string | null;
    turn_number?: number | null;
    page_url?: string | null;
  },
): Promise<{ ok: boolean }> {
  return apiSend<{ ok: boolean }>("/battle/bug-report", "POST", payload, token);
}

export async function joinBattleRoom(
  token: string | null | undefined,
  code: string,
  opts: { deckId?: string | null; deck?: BattleInlineDeck | null } = {},
): Promise<BattleRoomInfo> {
  return apiSend<BattleRoomInfo>(
    `/battle/rooms/${encodeURIComponent(code)}/join`,
    "POST",
    {
      ...(opts.deckId ? { deck_id: opts.deckId } : {}),
      ...(opts.deck ? { deck: opts.deck } : {}),
    },
    token,
  );
}

export async function setBattleRoomDeck(
  token: string | null | undefined,
  code: string,
  opts: { deckId?: string | null; deck?: BattleInlineDeck | null },
): Promise<BattleRoomInfo> {
  return apiSend<BattleRoomInfo>(
    `/battle/rooms/${encodeURIComponent(code)}/deck`,
    "POST",
    {
      ...(opts.deckId ? { deck_id: opts.deckId } : {}),
      ...(opts.deck ? { deck: opts.deck } : {}),
    },
    token,
  );
}

export async function setBattleRoomReady(
  token: string | null | undefined,
  code: string,
  ready: boolean,
): Promise<BattleRoomInfo> {
  return apiSend<BattleRoomInfo>(
    `/battle/rooms/${encodeURIComponent(code)}/ready`,
    "POST",
    { ready },
    token,
  );
}

export async function fetchBattleRoom(code: string): Promise<BattleRoomInfo> {
  const { data } = await apiGet<BattleRoomInfo>(`/battle/rooms/${encodeURIComponent(code)}`);
  return data;
}

export type BattleLiveRoomSummary = {
  room_code: string;
  mode: "ai" | "pvp" | "hotseat";
  status: string;
  turn_number: number;
  players: Array<{
    username: string;
    is_ai: boolean;
    leader_card_id: string | null;
  } | null>;
  spectator_count: number;
  show_hands: boolean;
};

export async function fetchLiveSpectatableRooms(
  mode: "all" | "ai" | "pvp" | "hotseat" = "all",
): Promise<BattleLiveRoomSummary[]> {
  const { data } = await apiGet<{ rooms: BattleLiveRoomSummary[] }>(
    `/battle/rooms/live?mode=${encodeURIComponent(mode)}`,
  );
  return data.rooms || [];
}

export type BattleMatchmakingStatus = {
  status: "idle" | "queued" | "matched";
  room_code?: string | null;
  queued?: number;
  waited_sec?: number;
  guest_token?: string | null;
  guest_user_id?: string | null;
  guest_username?: string | null;
  rating?: number;
  match_window?: number;
};

export type BattleRankProfile = {
  user_id: string;
  username?: string;
  rating: number;
  tier: string;
  tier_label_zh: string;
  elite_title: string | null;
  elite_title_zh: string | null;
  games: number;
  wins: number;
  losses: number;
  draws: number;
  win_rate: number;
  peak_rating: number;
  elite_pending?: boolean;
};

export type BattleRankLeaderboardEntry = BattleRankProfile & {
  rank: number;
};

export type BattleRankHistoryEntry = {
  room_code: string;
  replay_id?: string | null;
  opponent_user_id: string;
  opponent_username: string;
  rating_before: number;
  rating_after: number;
  delta: number;
  result: "win" | "loss" | "draw";
  created_at: number;
};

export async function joinBattleRanked(
  token: string,
  opts: {
    deckId?: string | null;
    deck?: BattleInlineDeck | null;
    allowSpectators?: boolean;
    spectatorShowHands?: boolean;
  },
): Promise<BattleMatchmakingStatus> {
  return apiSend<BattleMatchmakingStatus>(
    "/battle/ranked/join",
    "POST",
    {
      allow_spectators: opts.allowSpectators ?? true,
      spectator_show_hands: opts.spectatorShowHands ?? true,
      ...(opts.deckId ? { deck_id: opts.deckId } : {}),
      ...(opts.deck ? { deck: opts.deck } : {}),
    },
    token,
  );
}

export async function leaveBattleRanked(token: string): Promise<BattleMatchmakingStatus> {
  return apiSend<BattleMatchmakingStatus>("/battle/ranked/leave", "POST", {}, token);
}

export async function fetchBattleRankedStatus(token: string): Promise<BattleMatchmakingStatus> {
  const { data } = await apiGet<BattleMatchmakingStatus>("/battle/ranked/status", { token });
  return data;
}

export async function fetchBattleRankMe(token: string): Promise<BattleRankProfile> {
  const { data } = await apiGet<BattleRankProfile>("/battle/rank/me", { token });
  return data;
}

export async function fetchBattleRankLeaderboard(limit = 50): Promise<BattleRankLeaderboardEntry[]> {
  const { data } = await apiGet<{ entries: BattleRankLeaderboardEntry[] }>(
    `/battle/rank/leaderboard?limit=${encodeURIComponent(String(limit))}`,
  );
  return data.entries || [];
}

export async function fetchBattleRankElite(): Promise<Record<string, BattleRankLeaderboardEntry[]>> {
  const { data } = await apiGet<Record<string, BattleRankLeaderboardEntry[]>>("/battle/rank/elite");
  return data;
}

export async function fetchBattleRankHistory(
  token: string,
  limit = 20,
): Promise<BattleRankHistoryEntry[]> {
  const { data } = await apiGet<{ matches: BattleRankHistoryEntry[] }>(
    `/battle/rank/history?limit=${encodeURIComponent(String(limit))}`,
    { token },
  );
  return data.matches || [];
}

export type BattleRankAppealStatus = {
  ok?: boolean;
  status: "none" | "pending" | "approved" | "rejected" | "reverted";
  can_appeal?: boolean;
  appeal_id?: number;
  room_code?: string;
  error?: string;
};

export async function fetchBattleRankAppealStatus(
  token: string,
  roomCode: string,
): Promise<BattleRankAppealStatus> {
  const { data } = await apiGet<BattleRankAppealStatus>(
    `/battle/rank/appeal/status?room_code=${encodeURIComponent(roomCode)}`,
    { token },
  );
  return data;
}

export async function submitBattleRankAppeal(
  token: string,
  payload: { room_code: string; message: string; replay_id?: string | null },
): Promise<{ ok: boolean; appeal_id: number; status: string }> {
  return apiSend("/battle/rank/appeal", "POST", payload, token);
}

export async function joinBattleMatchmaking(
  token: string | null | undefined,
  opts: {
    deckId?: string | null;
    deck?: BattleInlineDeck | null;
    allowSpectators?: boolean;
    spectatorShowHands?: boolean;
  },
): Promise<BattleMatchmakingStatus> {
  return apiSend<BattleMatchmakingStatus>(
    "/battle/matchmaking/join",
    "POST",
    {
      allow_spectators: opts.allowSpectators ?? true,
      spectator_show_hands: opts.spectatorShowHands ?? true,
      ...(opts.deckId ? { deck_id: opts.deckId } : {}),
      ...(opts.deck ? { deck: opts.deck } : {}),
    },
    token,
  );
}

export async function leaveBattleMatchmaking(
  token: string | null | undefined,
): Promise<BattleMatchmakingStatus> {
  return apiSend<BattleMatchmakingStatus>("/battle/matchmaking/leave", "POST", {}, token);
}

export async function fetchBattleMatchmakingStatus(
  token: string | null | undefined,
): Promise<BattleMatchmakingStatus> {
  const { data } = await apiGet<BattleMatchmakingStatus>("/battle/matchmaking/status", { token });
  return data;
}

export type BattleReplaySummary = {
  id: string;
  mode: string;
  room_code: string;
  created_at: number;
  winner_seat: number | null;
  p0_username: string;
  p1_username: string;
  p0_leader: string;
  p1_leader: string;
  turn_number: number;
  frame_count: number;
};

export type BattleReplayHeader = {
  id: string;
  mode: string;
  room_code: string;
  created_at: number;
  finished_at: number;
  winner_seat: number | null;
  participant_ids: string[];
  p0: { user_id: string; username: string; leader_card_id: string; is_ai: boolean };
  p1: { user_id: string; username: string; leader_card_id: string; is_ai: boolean };
  turn_number: number;
  log: Array<{ key: string; [param: string]: unknown }>;
  frame_count: number;
};

export type BattleReplayFrame = Record<string, unknown> & {
  log_delta?: Array<{ key: string; [param: string]: unknown }>;
};

export type BattleReplayPayload = {
  header: BattleReplayHeader;
  frames: BattleReplayFrame[];
};

export async function fetchBattleReplays(token: string): Promise<BattleReplaySummary[]> {
  const { data } = await apiGet<{ matches: BattleReplaySummary[] }>("/battle/replays", { token });
  return data.matches || [];
}

export async function fetchBattleReplay(token: string, replayId: string): Promise<BattleReplayPayload> {
  const { data } = await apiGet<BattleReplayPayload>(
    `/battle/replays/${encodeURIComponent(replayId)}`,
    { token },
  );
  return data;
}

export async function createDeck(
  token: string,
  payload: { name: string; leader_card_id?: string | null; cards?: Record<string, number> },
): Promise<Deck> {
  return apiSend<Deck>("/decks", "POST", payload, token);
}

export async function updateDeck(
  token: string,
  deckId: string,
  payload: { name?: string | null; leader_card_id?: string | null; cards?: Record<string, number> },
): Promise<Deck> {
  return apiSend<Deck>(`/decks/${encodeURIComponent(deckId)}`, "PUT", payload, token);
}

export async function deleteDeck(token: string, deckId: string): Promise<void> {
  await apiSend(`/decks/${encodeURIComponent(deckId)}`, "DELETE", undefined, token);
}

export type DeckStatFields = {
  card_type?: string | null;
  cost?: number | null;
  counter?: number | null;
  power?: number | string | null;
  name?: string | null;
  name_en?: string | null;
  colors?: string[];
  rarity?: string | null;
  /** Pre-normalized name/trait blob for multilingual collection search. */
  search_blob?: string | null;
};

export async function fetchDeckStatsBatch(ids: string[]): Promise<Record<string, DeckStatFields>> {
  const unique = [...new Set(ids.map((x) => String(x || "").trim()).filter(Boolean))];
  if (!unique.length) return {};
  return apiSend<Record<string, DeckStatFields>>("/cards/deck-stats/batch", "POST", { ids: unique });
}

export async function fetchBinder(token: string): Promise<BinderResponse> {
  const { data } = await apiGet<BinderResponse>("/binder", { token });
  return data;
}

export async function binderSetSlot(
  token: string,
  page: number,
  slot: number,
  cardId: string | null,
): Promise<BinderResponse> {
  return apiSend<BinderResponse>("/binder/slot", "PUT", { page, slot, card_id: cardId }, token);
}

export async function binderSwap(
  token: string,
  page: number,
  fromSlot: number,
  toSlot: number,
): Promise<BinderResponse> {
  return apiSend<BinderResponse>(
    "/binder/swap",
    "PUT",
    { page, from_slot: fromSlot, to_slot: toSlot },
    token,
  );
}

export async function binderSetPageTitle(
  token: string,
  page: number,
  title: string,
): Promise<BinderResponse> {
  return apiSend<BinderResponse>("/binder/page-title", "PUT", { page, title }, token);
}

export async function binderClearPage(token: string, page: number): Promise<BinderResponse> {
  return apiSend<BinderResponse>(`/binder/clear-current-page?page=${page}`, "POST", {}, token);
}

export async function binderAutofillPage(token: string, page: number): Promise<BinderResponse> {
  return apiSend<BinderResponse>(`/binder/autofill-current-page?page=${page}`, "POST", {}, token);
}

export async function binderCreateShare(token: string): Promise<BinderShareCreateResponse> {
  return apiSend<BinderShareCreateResponse>("/binder/share", "POST", {}, token);
}

export async function fetchSharedBinder(shareToken: string): Promise<BinderSharedResponse> {
  const { data } = await apiGet<BinderSharedResponse>(`/binder/shared/${encodeURIComponent(shareToken)}`);
  return data;
}

export async function recognizePhoto(imageBase64: string): Promise<PhotoRecognizeResponse> {
  return apiSend<PhotoRecognizeResponse>("/recognize/photo", "POST", { image_base64: imageBase64 });
}

export async function fetchPrices(cardId: string): Promise<Record<string, unknown>> {
  const { data } = await apiGet<Record<string, unknown>>(`/prices/${encodeURIComponent(cardId)}`);
  return data;
}

/* ---- Community forum ---- */

export async function fetchCommunityCategories(opts?: {
  token?: string | null;
  admin?: boolean;
}): Promise<CommunityCategory[]> {
  const { data } = await apiGet<{ categories: CommunityCategory[] }>("/community/categories", {
    token: opts?.token,
    query: opts?.admin ? { admin: 1 } : undefined,
  });
  return data.categories;
}

export async function fetchCommunityTags(): Promise<CommunityTag[]> {
  const { data } = await apiGet<{ tags: CommunityTag[] }>("/community/tags");
  return data.tags;
}

export async function fetchCommunityThreads(opts?: {
  token?: string | null;
  category_id?: number | null;
  tag_id?: number | null;
  q?: string | null;
  sort?: string;
  limit?: number;
  offset?: number;
}): Promise<CommunityThreadListResult> {
  const { data } = await apiGet<CommunityThreadListResult>("/community/threads", {
    token: opts?.token,
    query: {
      category_id: opts?.category_id ?? undefined,
      tag_id: opts?.tag_id ?? undefined,
      q: opts?.q?.trim() || undefined,
      sort: opts?.sort || "new",
      limit: opts?.limit ?? 30,
      offset: opts?.offset ?? 0,
    },
  });
  return data;
}

export async function fetchCommunityMyThreads(
  token: string,
  opts?: { limit?: number; offset?: number },
): Promise<CommunityThreadListResult> {
  const { data } = await apiGet<CommunityThreadListResult>("/community/me/threads", {
    token,
    query: { limit: opts?.limit ?? 30, offset: opts?.offset ?? 0 },
  });
  return data;
}

export async function fetchCommunityMyPosts(
  token: string,
  opts?: { limit?: number; offset?: number },
): Promise<{ posts: CommunityPost[]; total: number; has_more: boolean; offset: number; limit: number }> {
  const { data } = await apiGet<{
    posts: CommunityPost[];
    total: number;
    has_more: boolean;
    offset: number;
    limit: number;
  }>("/community/me/posts", {
    token,
    query: { limit: opts?.limit ?? 30, offset: opts?.offset ?? 0 },
  });
  return data;
}

export async function fetchCommunityThread(
  id: number,
  token?: string | null,
): Promise<{ thread: CommunityThread; posts: CommunityPost[] }> {
  const { data } = await apiGet<{ thread: CommunityThread; posts: CommunityPost[] }>(
    `/community/threads/${id}`,
    { token },
  );
  return data;
}

export async function createCommunityThread(
  token: string,
  body: {
    category_id: number;
    title: string;
    body: string;
    anonymous?: boolean;
    tag_ids?: number[];
  },
): Promise<CommunityThread> {
  return apiSend<CommunityThread>("/community/threads", "POST", body, token);
}

export async function createCommunityPost(
  token: string,
  threadId: number,
  body: { body: string; anonymous?: boolean; parent_post_id?: number | null },
): Promise<CommunityPost> {
  return apiSend<CommunityPost>(`/community/threads/${threadId}/posts`, "POST", body, token);
}

export async function patchCommunityThread(
  token: string,
  threadId: number,
  body: { title?: string; body?: string; anonymous?: boolean },
): Promise<CommunityThread> {
  return apiSend<CommunityThread>(`/community/threads/${threadId}`, "PATCH", body, token);
}

export async function deleteCommunityThread(token: string, threadId: number): Promise<{ ok: boolean }> {
  return apiSend(`/community/threads/${threadId}`, "DELETE", undefined, token);
}

export async function patchCommunityPost(
  token: string,
  postId: number,
  body: { body?: string; anonymous?: boolean },
): Promise<CommunityPost> {
  return apiSend<CommunityPost>(`/community/posts/${postId}`, "PATCH", body, token);
}

export async function deleteCommunityPost(token: string, postId: number): Promise<{ ok: boolean }> {
  return apiSend(`/community/posts/${postId}`, "DELETE", undefined, token);
}

export async function likeCommunity(
  token: string,
  target_type: "thread" | "post",
  target_id: number,
  liked: boolean,
): Promise<{ like_count: number; liked_by_me: boolean }> {
  return apiSend("/community/likes", "POST", { target_type, target_id, liked }, token);
}

export async function reportCommunity(
  token: string,
  body: { target_type: "thread" | "post"; target_id: number; reason: string },
): Promise<{ ok: boolean; report_id: number }> {
  return apiSend("/community/reports", "POST", body, token);
}

export async function fetchCommunityAdminReports(
  token: string,
  status?: string | null,
): Promise<CommunityReport[]> {
  const { data } = await apiGet<{ reports: CommunityReport[] }>("/community/admin/reports", {
    token,
    query: { status: status ?? "open" },
  });
  return data.reports;
}

export async function patchCommunityReport(
  token: string,
  reportId: number,
  body: { status: string; note?: string },
): Promise<CommunityReport> {
  return apiSend(`/community/admin/reports/${reportId}`, "PATCH", body, token);
}

export async function patchCommunityAdminThread(
  token: string,
  threadId: number,
  body: { pinned?: boolean; locked?: boolean; deleted?: boolean },
): Promise<CommunityThread> {
  return apiSend(`/community/admin/threads/${threadId}`, "PATCH", body, token);
}

export async function patchCommunityAdminPost(
  token: string,
  postId: number,
  body: { deleted?: boolean },
): Promise<CommunityPost> {
  return apiSend(`/community/admin/posts/${postId}`, "PATCH", body, token);
}

export async function patchCommunityCategory(
  token: string,
  categoryId: number,
  active: boolean,
): Promise<CommunityCategory> {
  return apiSend(`/community/admin/categories/${categoryId}`, "PATCH", { active }, token);
}

export async function fetchCommunityAdminThreads(token: string): Promise<CommunityThreadListResult> {
  const { data } = await apiGet<CommunityThreadListResult>("/community/admin/threads", { token });
  return data;
}
