import { unstable_cache } from "next/cache";
import { ApiError, fetchCard, fetchCardTournaments, type CardDetailResponse } from "./api";
import {
  CardTemporarilyUnavailableError,
  fetchCardDetailUncached,
  fetchSecondaryUncached,
} from "./cardPageCache";

/**
 * Card text, rarity, and effects change only when the catalog is edited.
 * Six hours is long enough that a Googlebot pass over the same card URL
 * reuses this data cache, and short enough that a correction shows up the
 * same day. Prices are fetched in the browser and are not stored here.
 *
 * The card route reads searchParams (picked / pickedVariant), so the HTML
 * stays dynamic and those params are applied on every request. This cache
 * is only the card payload, keyed by card id, not by the query string.
 * A thrown render is therefore not stored as a full-page ISR entry.
 *
 * Fetch data cache: `fetchCard` uses `cache: "no-store"`. Tournament SSR
 * also passes `no-store`. Next.js 15 only writes a fetch response into the
 * data cache when the status is 200, and at request time `cache: "default"`
 * is treated as auto-no-cache. Connection failures never produce a response
 * to store.
 *
 * `unstable_cache` is different: it JSON-stores the callback's resolved
 * value, including `null`, for `revalidate` seconds, and it does not store a
 * throw. These callbacks therefore throw on 5xx, timeouts, connection
 * errors, and empty bodies. They never return null. A stale success is left
 * in place when background revalidation throws.
 */
export const CARD_DATA_REVALIDATE_SECONDS = 6 * 60 * 60;

type TournamentPayload = Awaited<ReturnType<typeof fetchCardTournaments>>;

function logUncached(kind: "card" | "card-tournaments", cardId: string, error: unknown) {
  const detail = error instanceof ApiError ? `HTTP ${error.status}` : error instanceof Error ? error.name : "error";
  console.warn(`[card-cache] not caching ${kind} cardId=${cardId} (${detail})`);
}

/**
 * Successful card payloads are cached. Failures throw and are not written.
 */
export async function getCachedCardDetail(cardId: string): Promise<CardDetailResponse> {
  let missed = false;
  const data = await unstable_cache(
    async (id: string) => {
      missed = true;
      console.info(`[card-cache] miss cardId=${id}`);
      try {
        return await fetchCardDetailUncached(id, (cid) => fetchCard(cid, false));
      } catch (error) {
        logUncached("card", id, error);
        throw error;
      }
    },
    ["card-detail-v2"],
    { revalidate: CARD_DATA_REVALIDATE_SECONDS },
  )(cardId);
  if (!data?.card) {
    // `unstable_cache` would serve a stored null until revalidate. Never treat
    // that as a successful hit or as a 404.
    throw new CardTemporarilyUnavailableError(`refusing cached empty card payload for ${cardId}`);
  }
  if (!missed) console.info(`[card-cache] hit cardId=${cardId}`);
  return data;
}

/**
 * Tournament rows are part of the server-rendered FAQ. A failure throws so
 * it is not cached as an empty list; the page omits that section instead of
 * failing the whole card document.
 */
export async function getCachedCardTournaments(
  cardId: string,
  limit: number,
): Promise<TournamentPayload> {
  let missed = false;
  const data = await unstable_cache(
    async (id: string, lim: number) => {
      missed = true;
      console.info(`[card-tournaments-cache] miss cardId=${id}`);
      try {
        return await fetchSecondaryUncached(() =>
          fetchCardTournaments(id, lim, { cache: "no-store" }),
        );
      } catch (error) {
        logUncached("card-tournaments", id, error);
        throw error;
      }
    },
    ["card-tournaments-v2"],
    { revalidate: CARD_DATA_REVALIDATE_SECONDS },
  )(cardId, limit);
  if (data == null) {
    throw new CardTemporarilyUnavailableError(`refusing cached empty tournaments for ${cardId}`);
  }
  if (!missed) console.info(`[card-tournaments-cache] hit cardId=${cardId}`);
  return data;
}
