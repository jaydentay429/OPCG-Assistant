/**
 * After a deploy, a tab opened on the previous build still requests JS
 * chunks that no longer exist. A full navigation is only safe when the
 * failure follows a real same-tab link click: that is the user asking to
 * change pages. Anything else (first load, a lazy panel) shows a prompt
 * and waits for the user. The sessionStorage timestamp is left in place;
 * the time window is what stops a navigation loop.
 */
export const CHUNK_RELOAD_STORAGE_KEY = "opcg-chunk-reload-at";

/** A second automatic navigation is allowed only after this much time has passed. */
export const CHUNK_RELOAD_WINDOW_MS = 10_000;

/**
 * A chunk error counts as caused by a link click only inside this window.
 * Long enough for the App Router to request the next page's chunk, short
 * enough that a later lazy import is not treated as that click.
 */
export const CHUNK_NAV_CLICK_WINDOW_MS = 5_000;

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

export type NavigationClickLike = {
  button?: number;
  metaKey?: boolean;
  ctrlKey?: boolean;
  shiftKey?: boolean;
  altKey?: boolean;
  target: EventTarget | null;
};

type AnchorLike = {
  href?: string;
  target?: string;
  getAttribute?: (name: string) => string | null;
  hasAttribute?: (name: string) => boolean;
};

function findAnchor(target: EventTarget | null): AnchorLike | null {
  if (!target || typeof target !== "object") return null;
  if ("closest" in target && typeof target.closest === "function") {
    const found = target.closest("a");
    return found && typeof found === "object" ? (found as AnchorLike) : null;
  }
  if ("parentElement" in target) {
    const parent = (target as { parentElement?: { closest?: (selector: string) => unknown } | null }).parentElement;
    if (parent && typeof parent.closest === "function") {
      const found = parent.closest("a");
      return found && typeof found === "object" ? (found as AnchorLike) : null;
    }
  }
  return null;
}

/**
 * Absolute same-origin URL for a primary click on an in-app link.
 * Modifier-clicks, new tabs, downloads, external URLs, and hash-only
 * changes return null — those do not replace this document.
 */
export function internalNavigationHrefFromClick(event: NavigationClickLike, currentHref: string): string | null {
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return null;
  if (event.button != null && event.button !== 0) return null;

  const anchor = findAnchor(event.target);
  if (!anchor) return null;
  if (typeof anchor.hasAttribute === "function" && anchor.hasAttribute("download")) return null;
  if (typeof anchor.getAttribute === "function" && anchor.getAttribute("download") !== null) return null;

  const targetAttr = (anchor.getAttribute?.("target") ?? anchor.target ?? "").trim().toLowerCase();
  if (targetAttr && targetAttr !== "_self" && targetAttr !== "_parent" && targetAttr !== "_top") return null;

  const raw = anchor.getAttribute?.("href");
  let next: URL;
  try {
    if (typeof raw === "string" && raw.trim() !== "") next = new URL(raw, currentHref);
    else if (typeof anchor.href === "string" && anchor.href) next = new URL(anchor.href, currentHref);
    else return null;
  } catch {
    return null;
  }
  if (next.protocol !== "http:" && next.protocol !== "https:") return null;

  let current: URL;
  try {
    current = new URL(currentHref);
  } catch {
    return null;
  }
  if (next.origin !== current.origin) return null;
  if (next.pathname === current.pathname && next.search === current.search) return null;
  return next.href;
}

let pendingNavigation: { href: string; at: number } | null = null;

export function recordInternalNavigationClick(href: string, at = Date.now()) {
  pendingNavigation = { href, at };
}

export function clearPendingNavigation() {
  pendingNavigation = null;
}

export function recentInternalNavigationHref(now = Date.now()): string | null {
  if (!pendingNavigation) return null;
  const age = now - pendingNavigation.at;
  if (age < 0 || age > CHUNK_NAV_CLICK_WINDOW_MS) return null;
  return pendingNavigation.href;
}

/**
 * Go to the clicked URL at most once per window.
 * Returns false when storage is unavailable (private mode can throw) or the
 * previous automatic navigation is still inside the window.
 */
export function assignOnceForChunkNavigation(href: string, now = Date.now()): boolean {
  try {
    const stored = sessionStorage.getItem(CHUNK_RELOAD_STORAGE_KEY);
    const previous = stored === null || stored === "" ? Number.NaN : Number(stored);
    if (Number.isFinite(previous) && now - previous < CHUNK_RELOAD_WINDOW_MS) {
      return false;
    }
    sessionStorage.setItem(CHUNK_RELOAD_STORAGE_KEY, String(now));
    window.location.assign(href);
    return true;
  } catch {
    return false;
  }
}

export type ChunkRecovery = "assigned" | "prompt" | "ignored";

/** Assign only for a recent in-app link click. Every other chunk failure asks the user. */
export function handleChunkLoadFailure(value: unknown, now = Date.now()): ChunkRecovery {
  if (!isChunkLoadError(value)) return "ignored";
  const href = recentInternalNavigationHref(now);
  if (href && assignOnceForChunkNavigation(href, now)) return "assigned";
  return "prompt";
}

type ChunkListener = (event: Event) => void;

export type ChunkLoadEventTarget = {
  addEventListener(type: string, listener: ChunkListener, capture?: boolean): void;
  removeEventListener(type: string, listener: ChunkListener, capture?: boolean): void;
};

export type ChunkRecoveryOptions = {
  windowTarget?: ChunkLoadEventTarget;
  documentTarget?: ChunkLoadEventTarget;
  currentHref?: () => string;
  now?: () => number;
  onPrompt?: () => void;
};

function outcomeForEvent(event: Event, now: () => number): ChunkRecovery {
  const errorEvent = event as ErrorEvent & { reason?: unknown };
  const primary = "reason" in event ? errorEvent.reason : errorEvent.error;
  const first = handleChunkLoadFailure(primary, now());
  if (first !== "ignored") return first;
  return handleChunkLoadFailure(errorEvent.message, now());
}

/** Browser-only. No-ops during SSR so the root layout can mount the caller. */
export function attachChunkLoadRecovery(options?: ChunkRecoveryOptions): () => void {
  if (typeof window === "undefined" && !options?.windowTarget && !options?.documentTarget) return () => {};
  const windowTarget = options?.windowTarget ?? window;
  const documentTarget = options?.documentTarget ?? document;
  const currentHref = options?.currentHref ?? (() => window.location.href);
  const now = options?.now ?? Date.now;
  const onPrompt = options?.onPrompt ?? (() => {});

  const onClick = (event: Event) => {
    const href = internalNavigationHrefFromClick(event as NavigationClickLike, currentHref());
    if (href) recordInternalNavigationClick(href, now());
    else clearPendingNavigation();
  };
  const onFailure = (event: Event) => {
    if (outcomeForEvent(event, now) === "prompt") onPrompt();
  };

  documentTarget.addEventListener("click", onClick, true);
  windowTarget.addEventListener("error", onFailure);
  windowTarget.addEventListener("unhandledrejection", onFailure);
  return () => {
    documentTarget.removeEventListener("click", onClick, true);
    windowTarget.removeEventListener("error", onFailure);
    windowTarget.removeEventListener("unhandledrejection", onFailure);
  };
}
