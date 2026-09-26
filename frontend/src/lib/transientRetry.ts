import { ApiError } from "./api";

/** One extra attempt after a timeout, network error, or 5xx. */
export const TRANSIENT_RETRY_LIMIT = 1;

/** Short pause so a blip can clear without holding the render for long. */
export const TRANSIENT_RETRY_DELAY_MS = 200;

/**
 * Timeouts (408), transport failures, and 5xx are worth one more try.
 * 404 and 422 are definitive answers from the API. Other 4xx are not transient.
 */
export function isTransientApiFailure(error: unknown): boolean {
  if (error instanceof ApiError) {
    if (error.status === 404 || error.status === 422) return false;
    if (error.status === 408 || (error.status >= 500 && error.status <= 599)) return true;
    return false;
  }
  return true;
}

function failureLabel(error: unknown): string {
  if (error instanceof ApiError) return `HTTP ${error.status}`;
  if (error instanceof Error && error.name) return error.name;
  return "network";
}

export async function withTransientRetry<T>(
  fn: () => Promise<T>,
  opts?: {
    retries?: number;
    delayMs?: number;
    sleep?: (ms: number) => Promise<void>;
  },
): Promise<T> {
  const retries = opts?.retries ?? TRANSIENT_RETRY_LIMIT;
  const delayMs = opts?.delayMs ?? TRANSIENT_RETRY_DELAY_MS;
  const sleep =
    opts?.sleep ?? ((ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms)));
  let attempt = 0;
  for (;;) {
    try {
      return await fn();
    } catch (error) {
      if (attempt >= retries || !isTransientApiFailure(error)) throw error;
      attempt += 1;
      console.warn(`[card-fetch] transient ${failureLabel(error)}, retrying once`);
      if (delayMs > 0) await sleep(delayMs);
    }
  }
}
