import { unstable_cache } from "next/cache";
import { ApiError, fetchCard, fetchCardTournaments, type CardDetailResponse } from "./api";
import { withTransientRetry } from "./transientRetry";

/**
 * Card text, rarity, and effects change only when the catalog is edited.
 * Six hours is long enough that a Googlebot pass over the same card URL
 * reuses this data cache, and short enough that a correction shows up the
 * same day. Prices are fetched in the browser and are not stored here.
 *
 * The card route reads searchParams (picked / pickedVariant), so the HTML
 * stays dynamic and those params are applied on every request. This cache
 * is only the card payload, keyed by card id, not by the query string.
 *
 * Only a successful return value is stored. Timeouts, network errors, 5xx,
 * 404/422, and a 200 with no card throw, so they are not kept for the
 * revalidate window.
 */
export const CARD_DATA_REVALIDATE_SECONDS = 6 * 60 * 60;

type TournamentPayload = Awaited<ReturnType<typeof fetchCardTournaments>>;

async function readCardOrigin(cardId: string): Promise<CardDetailResponse> {
  console.info(`[card-cache] miss cardId=${cardId}`);
  const data = await withTransientRetry(() => fetchCard(cardId, false));
  if (!data?.card) {
    throw new ApiError(404, `Card API returned no card for ${cardId}`);
  }
  return data;
}

async function readTournamentsOrigin(cardId: string, limit: number): Promise<TournamentPayload> {
  console.info(`[card-tournaments-cache] miss cardId=${cardId}`);
  return withTransientRetry(() => fetchCardTournaments(cardId, limit));
}

/**
 * Successful card payloads are cached. Failures throw and are not written.
 */
export async function getCachedCardDetail(cardId: string): Promise<CardDetailResponse> {
  let missed = false;
  const data = await unstable_cache(
    async (id: string) => {
      missed = true;
      return readCardOrigin(id);
    },
    ["card-detail-v1"],
    { revalidate: CARD_DATA_REVALIDATE_SECONDS },
  )(cardId);
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
      return readTournamentsOrigin(id, lim);
    },
    ["card-tournaments-v1"],
    { revalidate: CARD_DATA_REVALIDATE_SECONDS },
  )(cardId, limit);
  if (!missed) console.info(`[card-tournaments-cache] hit cardId=${cardId}`);
  return data;
}
