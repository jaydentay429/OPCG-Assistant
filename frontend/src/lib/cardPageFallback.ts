import { ApiError } from "./api";
import { normalizeCatalogCardId } from "./cardCatalog";
import { isDefinitiveCardMiss } from "./cardPageCache";
import type { Card, CardDetailResponse } from "./types";
import type { Metadata } from "next";

/** Same window as `CardTemporarilyUnavailableError.retryAfterSeconds`. */
export const CARD_PAGE_RETRY_AFTER_SECONDS = 10;

/**
 * Retry state for a card URL that has no API payload and no bundled row.
 * Do not set robots/noindex here. A normal card render keeps the layout's
 * index,follow tags; this response is temporary only because of HTTP 503.
 */
export const cardUnavailableMetadata: Metadata = {
  title: "卡牌暫時無法載入",
  description: "資料服務暫時沒有回應，請稍後再試。",
};

export type CardPageLoad =
  | { kind: "card"; card: Card; source: "api" | "memory" | "static" }
  | { kind: "missing" }
  | { kind: "unavailable"; retryAfterSeconds: number };

export type CardPageLoadOptions = {
  /** True when the bundled index contains this id. Called only after a definitive miss. */
  knownInCatalog: () => boolean;
  /** Local card row. Called only when the API did not answer. */
  readStatic: (cardId: string) => Card | null;
  /** Last successful API payloads for this process. Not written on failure. */
  memory: Map<string, Card>;
};

function memoryKey(cardId: string): string {
  return normalizeCatalogCardId(cardId);
}

/**
 * One card-detail attempt, then local data.
 *
 * The API call is the caller's existing 5s, no-retry fetch. This does not
 * call it again. A definitive 404/422 for an id the index does not know is
 * still a 404. Anything else falls back to the last successful payload, then
 * the bundled row. With neither, the page renders a retry state instead of 500.
 */
export async function resolveCardPageLoad(
  cardId: string,
  load: () => Promise<CardDetailResponse>,
  options: CardPageLoadOptions,
): Promise<CardPageLoad> {
  const key = memoryKey(cardId);
  let failure: unknown = null;
  try {
    const data = await load();
    if (data?.card) {
      options.memory.set(key, data.card);
      return { kind: "card", card: data.card, source: "api" };
    }
    failure = new ApiError(404, `Card API returned no card for ${cardId}`);
  } catch (error) {
    failure = error;
  }

  if (isDefinitiveCardMiss(failure) && !options.knownInCatalog()) {
    return { kind: "missing" };
  }

  const remembered = options.memory.get(key);
  if (remembered) return { kind: "card", card: remembered, source: "memory" };

  const bundled = options.readStatic(cardId);
  if (bundled) return { kind: "card", card: bundled, source: "static" };

  return { kind: "unavailable", retryAfterSeconds: CARD_PAGE_RETRY_AFTER_SECONDS };
}
