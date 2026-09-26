/**
 * After a deploy, a tab opened on the previous build still has the old
 * client router. Client navigations then request JS chunks that no longer
 * exist. Reloading once picks up the new build. The sessionStorage timestamp
 * is left in place; the time window is what stops a reload loop.
 */
export const CHUNK_RELOAD_STORAGE_KEY = "opcg-chunk-reload-at";

/** A second automatic reload is allowed only after this much time has passed. */
export const CHUNK_RELOAD_WINDOW_MS = 10_000;

const CHUNK_LOAD_MESSAGE_PATTERNS: readonly RegExp[] = [
  /Loading chunk \S+ failed/,
  /Failed to fetch dynamically imported module/,
  /Importing a module script failed/,
];

function textIsChunkLoadFailure(text: string): boolean {
  if (text.includes("ChunkLoadError")) return true;
  return CHUNK_LOAD_MESSAGE_PATTERNS.some((pattern) => pattern.test(text));
}

/** ChunkLoadError from webpack, plus the Chrome / Safari dynamic-import failures. */
export function isChunkLoadError(value: unknown): boolean {
  if (typeof value === "string") return textIsChunkLoadFailure(value);
  if (!value || typeof value !== "object") return false;
  const record = value as { name?: unknown; message?: unknown };
  if (record.name === "ChunkLoadError") return true;
  return typeof record.message === "string" && textIsChunkLoadFailure(record.message);
}

/**
 * Reload the current document at most once per window.
 * Returns false when storage is unavailable (private mode can throw) or the
 * previous reload is still inside the window — in both cases nothing reloads.
 */
export function reloadOnceForChunkError(now = Date.now()): boolean {
  try {
    const stored = sessionStorage.getItem(CHUNK_RELOAD_STORAGE_KEY);
    const previous = stored === null || stored === "" ? Number.NaN : Number(stored);
    if (Number.isFinite(previous) && now - previous < CHUNK_RELOAD_WINDOW_MS) {
      return false;
    }
    sessionStorage.setItem(CHUNK_RELOAD_STORAGE_KEY, String(now));
    window.location.reload();
    return true;
  } catch {
    return false;
  }
}

export function recoverFromChunkLoadError(value: unknown, now = Date.now()): boolean {
  if (!isChunkLoadError(value)) return false;
  return reloadOnceForChunkError(now);
}

type ChunkListener = (event: Event) => void;

export type ChunkLoadEventTarget = {
  addEventListener(type: string, listener: ChunkListener): void;
  removeEventListener(type: string, listener: ChunkListener): void;
};

/** Browser-only. No-ops during SSR so the root layout can mount the caller. */
export function attachChunkLoadRecovery(target?: ChunkLoadEventTarget): () => void {
  if (!target && typeof window === "undefined") return () => {};
  const resolved = target ?? window;

  const onError = (event: Event) => {
    const errorEvent = event as ErrorEvent;
    if (recoverFromChunkLoadError(errorEvent.error)) return;
    recoverFromChunkLoadError(errorEvent.message);
  };
  const onUnhandledRejection = (event: Event) => {
    recoverFromChunkLoadError((event as PromiseRejectionEvent).reason);
  };

  resolved.addEventListener("error", onError);
  resolved.addEventListener("unhandledrejection", onUnhandledRejection);
  return () => {
    resolved.removeEventListener("error", onError);
    resolved.removeEventListener("unhandledrejection", onUnhandledRejection);
  };
}
