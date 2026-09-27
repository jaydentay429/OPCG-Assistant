import { ApiError } from "./api";
import { missingCardShould404 } from "./cardCatalog";
import type { Card, CardDetailResponse } from "./types";
import { withTransientRetry } from "./transientRetry";

/**
 * Thrown when the card API did not give a definitive answer (5xx, timeout,
 * connection failure, or retries exhausted). This is not a 404.
 *
 * Next.js App Router turns an uncaught page error into HTTP 500. There is no
 * supported way for a Server Component to set 503 without middleware.
 */
export class CardTemporarilyUnavailableError extends Error {
  readonly retryAfterSeconds = 10;

  constructor(message: string, options?: { cause?: unknown }) {
    super(message, options?.cause !== undefined ? { cause: options.cause } : undefined);
    this.name = "CardTemporarilyUnavailableError";
  }
}

export type SuccessCacheStore<T> = {
  get(key: string): T | undefined;
  set(key: string, value: T): void;
};

type RetryOpts = {
  retries?: number;
  delayMs?: number;
  sleep?: (ms: number) => Promise<void>;
};

/** 404 and 422 are the API saying this id is not a card. Everything else is transient. */
export function isDefinitiveCardMiss(error: unknown): error is ApiError {
  return error instanceof ApiError && (error.status === 404 || error.status === 422);
}

/**
 * Remember a resolved success only.
 *
 * `unstable_cache` persists whatever the callback returns, including `null`,
 * for the whole revalidate window. It does not persist a throw. A wrapper that
 * catches a 502 and returns null would therefore be cached as "no card".
 * This store matches the "resolved values are stored" rule and additionally
 * refuses null/undefined so that footgun cannot be written.
 */
export async function readThroughSuccessCache<T>(
  store: SuccessCacheStore<T>,
  key: string,
  load: () => Promise<T | null | undefined>,
): Promise<T> {
  const hit = store.get(key);
  if (hit !== undefined) return hit;
  const value = await load();
  if (value == null) {
    throw new CardTemporarilyUnavailableError("refusing to cache an empty payload");
  }
  store.set(key, value);
  return value;
}

export function createMapStore<T>(): SuccessCacheStore<T> & { size(): number; has(key: string): boolean } {
  const map = new Map<string, T>();
  return {
    get(key) {
      return map.get(key);
    },
    set(key, value) {
      map.set(key, value);
    },
    size() {
      return map.size;
    },
    has(key) {
      return map.has(key);
    },
  };
}

export type CardDetailFetcher = (
  cardId: string,
) => Promise<CardDetailResponse | null | undefined>;

/**
 * Load one card for the cache callback. Throws on every failure so the caller
 * must not write the result. A 200 body without a card is a definitive miss
 * (same as HTTP 404), not a transient outage.
 */
export async function fetchCardDetailUncached(
  cardId: string,
  fetchCardImpl: CardDetailFetcher,
  retry?: RetryOpts,
): Promise<CardDetailResponse> {
  let data: CardDetailResponse | null | undefined;
  try {
    data = await withTransientRetry(() => fetchCardImpl(cardId), retry);
  } catch (error) {
    if (isDefinitiveCardMiss(error)) throw error;
    throw new CardTemporarilyUnavailableError(`Card API temporarily unavailable for ${cardId}`, {
      cause: error,
    });
  }
  if (!data?.card) {
    throw new ApiError(404, `Card API returned no card for ${cardId}`);
  }
  return data;
}

/**
 * Same rule for tournaments / other secondary payloads: a throw is not a
 * cacheable empty list. A resolved object (even with `items: []`) is a real
 * answer and may be stored by the caller.
 */
export async function fetchSecondaryUncached<T>(
  load: () => Promise<T | null | undefined>,
  retry?: RetryOpts,
): Promise<T> {
  let data: T | null | undefined;
  try {
    data = await withTransientRetry(load, retry);
  } catch (error) {
    throw new CardTemporarilyUnavailableError("secondary API temporarily unavailable", {
      cause: error,
    });
  }
  if (data == null) {
    throw new CardTemporarilyUnavailableError("secondary API returned an empty payload");
  }
  return data;
}

/**
 * Page decision shared with `loadCard`: definitive miss → null (`notFound()`),
 * anything else → throw (App Router responds 500, not an empty 200).
 */
export async function loadRenderableCard(
  cardId: string,
  load: () => Promise<CardDetailResponse>,
  knownInCatalog: boolean,
): Promise<Card | null> {
  try {
    const data = await load();
    if (data?.card) return data.card;
    if (!missingCardShould404(null, knownInCatalog)) {
      throw new CardTemporarilyUnavailableError(`Card API returned no card for catalogued id ${cardId}`);
    }
    return null;
  } catch (error) {
    if (isDefinitiveCardMiss(error) && missingCardShould404(error.status, knownInCatalog)) {
      return null;
    }
    throw error;
  }
}
