import { cache } from "react";
import { workAsyncStorage } from "next/dist/server/app-render/work-async-storage.external";
import { fetchCard } from "./api";
import { fetchCardDetailUncached, shareInflight } from "./cardPageCache";
import type { CardDetailResponse } from "./types";

/**
 * Card HTML has to fail fast when the API hangs. A 15s timeout plus one
 * retry, done from both generateMetadata and the page, holds the document
 * for about a minute and Googlebot cuts the crawl rate.
 * Other `fetchCard` callers keep the 15s default and their own retry policy.
 */
export const CARD_PAGE_FETCH_TIMEOUT_MS = 5000;

const requestMemos = new WeakMap<object, Map<string, Promise<CardDetailResponse>>>();
let warnedMissingStore = false;

function memoForThisRequest(): Map<string, Promise<CardDetailResponse>> | null {
  try {
    const store = workAsyncStorage.getStore();
    if (!store) return null;
    let memo = requestMemos.get(store);
    if (!memo) {
      memo = new Map();
      requestMemos.set(store, memo);
    }
    return memo;
  } catch (error) {
    console.warn("[card-fetch] request memo unavailable", error);
    return null;
  }
}

function loadCardPageDetail(cardId: string): Promise<CardDetailResponse> {
  console.info(`[card-fetch] cardId=${cardId} timeoutMs=${CARD_PAGE_FETCH_TIMEOUT_MS} retries=0`);
  return fetchCardDetailUncached(
    cardId,
    (cid) => fetchCard(cid, false, { timeoutMs: CARD_PAGE_FETCH_TIMEOUT_MS }),
    { retries: 0 },
  );
}

/**
 * One card-detail HTTP call for this request.
 *
 * React `cache()` shares the call inside a single render pass, which is what
 * `generateMetadata` and the page use when Next renders them together.
 * Those two can also run as separate passes, each with its own React cache,
 * so the in-flight promise is stored on the request WorkStore as well.
 * A timeout or 5xx still rejects: it is not written to the 6h data cache,
 * and the next request tries the API again.
 */
export const fetchCardDetailForPage = cache((cardId: string): Promise<CardDetailResponse> => {
  const memo = memoForThisRequest();
  if (!memo) {
    if (!warnedMissingStore) {
      warnedMissingStore = true;
      console.warn("[card-fetch] no request store; card detail fetch is not shared across render passes");
    }
    return loadCardPageDetail(cardId);
  }
  if (memo.has(cardId)) console.info(`[card-fetch] reuse cardId=${cardId}`);
  return shareInflight(memo, cardId, () => loadCardPageDetail(cardId));
});
