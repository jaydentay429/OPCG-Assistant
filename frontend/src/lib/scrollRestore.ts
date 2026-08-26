const SKIP_KEY = "opcg_skip_scroll_restore";
const SEARCH_STATE_KEY = "opcg_search_state_v1";
const BUILDER_SCROLL_KEY = "opcg_builder_scroll_v1";
const COLLECTOR_PREFS_KEY = "opcg_collector_prefs_v1";
const PRICES_PREFS_KEY = "opcg_prices_prefs_v1";
const CARD_DETAIL_SCROLL_KEY = "opcg_card_detail_scroll_v1";

export type ScrollTarget = {
  y: number;
  anchor?: string;
};

type RestoreJob = {
  y: number;
  anchor: string;
  startedAt: number;
  applied: boolean;
  ignoreScroll: boolean;
  onDone?: () => void;
};

let job: RestoreJob | null = null;
let raf = 0;
let ro: ResizeObserver | null = null;
let guardsAttached = false;
let defendTimer = 0;

function maxScrollY() {
  return Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
}

function clearDefendTimer() {
  if (defendTimer) {
    window.clearTimeout(defendTimer);
    defendTimer = 0;
  }
}

function finishJob() {
  const done = job?.onDone;
  job = null;
  clearDefendTimer();
  if (raf) {
    cancelAnimationFrame(raf);
    raf = 0;
  }
  if (ro) {
    ro.disconnect();
    ro = null;
  }
  detachUserGuards();
  try {
    done?.();
  } catch {
    /* ignore */
  }
}

function programmaticScroll(top: number) {
  if (!job) return;
  job.ignoreScroll = true;
  window.scrollTo({ top, behavior: "auto" });
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      if (job) job.ignoreScroll = false;
    });
  });
}

function findAnchor(id: string): HTMLElement | null {
  if (!id || typeof document === "undefined") return null;
  try {
    return document.querySelector(`[data-scroll-anchor="${CSS.escape(id)}"]`);
  } catch {
    return document.querySelector(`[data-scroll-anchor="${id.replace(/"/g, "")}"]`);
  }
}

/** Prefer scrolling the clicked card into view; fall back to pixel Y. */
function applyTarget(): boolean {
  if (!job) return false;
  if (job.anchor) {
    const el = findAnchor(job.anchor);
    if (el) {
      job.ignoreScroll = true;
      el.scrollIntoView({ block: "center", inline: "nearest", behavior: "auto" });
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          if (job) job.ignoreScroll = false;
        });
      });
      job.applied = true;
      attachUserGuards();
      return true;
    }
    // Keep waiting for the card node before using pixel Y.
    if (performance.now() - job.startedAt < 6000) return false;
  }
  if (job.y > 0) {
    const maxY = maxScrollY();
    if (maxY >= job.y - 8 || performance.now() - job.startedAt > 8000) {
      programmaticScroll(Math.max(0, Math.min(job.y, maxY)));
      job.applied = true;
      attachUserGuards();
      return true;
    }
  }
  return false;
}

function onScroll() {
  if (!job || job.ignoreScroll) return;
  const cur = window.scrollY || 0;
  if (job.applied && (job.y > 40 || job.anchor) && cur <= 8) {
    applyTarget();
    return;
  }
  if (job.applied && job.y > 0) {
    const target = Math.min(job.y, maxScrollY());
    if (Math.abs(cur - target) > 120) finishJob();
  }
}

function onUserScrollIntent() {
  if (!job?.applied) return;
  finishJob();
}

function attachUserGuards() {
  if (guardsAttached || typeof window === "undefined") return;
  guardsAttached = true;
  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("wheel", onUserScrollIntent, { passive: true });
  window.addEventListener("touchmove", onUserScrollIntent, { passive: true });
  window.addEventListener("keydown", onUserScrollIntent, { passive: true });
}

function detachUserGuards() {
  if (!guardsAttached || typeof window === "undefined") return;
  guardsAttached = false;
  window.removeEventListener("scroll", onScroll);
  window.removeEventListener("wheel", onUserScrollIntent);
  window.removeEventListener("touchmove", onUserScrollIntent);
  window.removeEventListener("keydown", onUserScrollIntent);
}

function tick() {
  raf = 0;
  if (!job) return;

  if (applyTarget()) {
    clearDefendTimer();
    defendTimer = window.setTimeout(() => {
      defendTimer = 0;
      if (job?.applied) finishJob();
    }, 1600);
    return;
  }

  // Waiting for the card node / page height. Leave top only if stuck at 0.
  if (maxScrollY() > 0 && (window.scrollY || 0) <= 8 && job.y > 0) {
    programmaticScroll(Math.min(job.y, maxScrollY()));
  }

  if (performance.now() - job.startedAt > 10000) {
    // Give up gracefully.
    if (job.y > 0) programmaticScroll(Math.min(job.y, maxScrollY()));
    job.applied = true;
    finishJob();
    return;
  }

  raf = requestAnimationFrame(tick);
}

function ensureResizeWatch() {
  if (ro || typeof ResizeObserver === "undefined") return;
  try {
    ro = new ResizeObserver(() => {
      if (!job || job.applied) return;
      if (raf) cancelAnimationFrame(raf);
      raf = requestAnimationFrame(tick);
    });
    ro.observe(document.documentElement);
    if (document.body) ro.observe(document.body);
  } catch {
    ro = null;
  }
}

function observeForAnchor(anchor: string) {
  if (!anchor || typeof MutationObserver === "undefined") return;
  const mo = new MutationObserver(() => {
    if (!job || job.applied) {
      mo.disconnect();
      return;
    }
    if (findAnchor(anchor)) {
      mo.disconnect();
      if (raf) cancelAnimationFrame(raf);
      raf = requestAnimationFrame(tick);
    }
  });
  mo.observe(document.body, { childList: true, subtree: true });
  window.setTimeout(() => mo.disconnect(), 12000);
}

/** performance.now() deadline — survives Strict Mode remounts (unlike one-shot session flag). */
let tabNavSkipUntil = 0;

function forceWindowTop() {
  if (typeof window === "undefined") return;
  window.scrollTo({ top: 0, behavior: "auto" });
  requestAnimationFrame(() => {
    window.scrollTo({ top: 0, behavior: "auto" });
  });
}

/** Bottom-nav tab switches: start at top, don't restore prior scroll. */
export function markTabNavScrollReset() {
  if (job) job.onDone = undefined;
  finishJob();
  tabNavSkipUntil = performance.now() + 2500;
  try {
    sessionStorage.setItem(SKIP_KEY, "1");
  } catch {
    /* ignore */
  }
  forceWindowTop();
}

/** True while a bottom-nav tab switch should keep the page pinned to top. */
export function isTabNavScrollResetPending(): boolean {
  if (typeof performance !== "undefined" && performance.now() < tabNavSkipUntil) return true;
  try {
    return sessionStorage.getItem(SKIP_KEY) === "1";
  } catch {
    return false;
  }
}

/**
 * Returns true when the next page should skip scroll restore (tab switch).
 * Uses a short time window so React Strict Mode remounts still see the skip.
 */
export function consumeSkipScrollRestore(): boolean {
  const timed = typeof performance !== "undefined" && performance.now() < tabNavSkipUntil;
  let flagged = false;
  try {
    if (sessionStorage.getItem(SKIP_KEY) === "1") {
      sessionStorage.removeItem(SKIP_KEY);
      flagged = true;
    }
  } catch {
    /* ignore */
  }
  if (timed || flagged) {
    forceWindowTop();
    return true;
  }
  return false;
}

/** Call on tab-root route changes to beat App Router scroll restoration. */
export function applyTabNavScrollTopIfNeeded() {
  if (!isTabNavScrollResetPending()) return false;
  forceWindowTop();
  return true;
}

/** Prefer a pending restore target so an early save at y=0 can't wipe it. */
export function scrollYForPersist(pendingY: number, currentY: number): number {
  if (pendingY > 0) return Math.floor(pendingY);
  if (job && job.y > 0 && !job.applied) return Math.floor(job.y);
  return Math.max(0, Math.floor(currentY || 0));
}

export function readPathScrollTarget(pathname?: string): ScrollTarget {
  const path = pathname || (typeof window !== "undefined" ? window.location.pathname : "/") || "/";
  try {
    if (path === "/" || path === "") {
      const raw = sessionStorage.getItem(SEARCH_STATE_KEY);
      if (!raw) return { y: 0 };
      const parsed = JSON.parse(raw) as { y?: unknown; anchor?: unknown };
      const y = Number(parsed.y);
      const anchor = typeof parsed.anchor === "string" ? parsed.anchor : "";
      return {
        y: Number.isFinite(y) && y > 0 ? Math.floor(y) : 0,
        anchor: anchor || undefined,
      };
    }
    if (path.startsWith("/builder")) {
      const raw = sessionStorage.getItem(BUILDER_SCROLL_KEY);
      if (!raw) return { y: 0 };
      if (raw.startsWith("{")) {
        const parsed = JSON.parse(raw) as { y?: unknown; anchor?: unknown };
        const y = Number(parsed.y);
        const anchor = typeof parsed.anchor === "string" ? parsed.anchor : "";
        return {
          y: Number.isFinite(y) && y > 0 ? Math.floor(y) : 0,
          anchor: anchor || undefined,
        };
      }
      const y = Number(raw);
      return { y: Number.isFinite(y) && y > 0 ? Math.floor(y) : 0 };
    }
    if (path.startsWith("/collector")) {
      const raw = localStorage.getItem(COLLECTOR_PREFS_KEY);
      if (!raw) return { y: 0 };
      const parsed = JSON.parse(raw) as { y?: unknown; anchor?: unknown };
      const y = Number(parsed.y);
      const anchor = typeof parsed.anchor === "string" ? parsed.anchor : "";
      return {
        y: Number.isFinite(y) && y > 0 ? Math.floor(y) : 0,
        anchor: anchor || undefined,
      };
    }
    if (path.startsWith("/prices")) {
      const raw = localStorage.getItem(PRICES_PREFS_KEY);
      if (!raw) return { y: 0 };
      const parsed = JSON.parse(raw) as { market?: { scrollY?: unknown; scrollAnchor?: unknown } };
      const market = parsed.market || {};
      const y = Number(market.scrollY);
      const anchor = typeof market.scrollAnchor === "string" ? market.scrollAnchor : "";
      return {
        y: Number.isFinite(y) && y > 0 ? Math.floor(y) : 0,
        anchor: anchor || undefined,
      };
    }
    if (path.startsWith("/cards/")) {
      const raw = sessionStorage.getItem(CARD_DETAIL_SCROLL_KEY);
      if (!raw) return { y: 0 };
      const parsed = JSON.parse(raw) as { path?: unknown; y?: unknown; anchor?: unknown };
      if (typeof parsed.path === "string" && parsed.path !== path) return { y: 0 };
      const y = Number(parsed.y);
      const anchor = typeof parsed.anchor === "string" ? parsed.anchor : "";
      return {
        y: Number.isFinite(y) && y > 0 ? Math.floor(y) : 0,
        anchor: anchor || undefined,
      };
    }
  } catch {
    /* ignore */
  }
  return { y: 0 };
}

/**
 * Start / refresh a restore job — blocked briefly after bottom-nav tab switches.
 */
export function requestScrollRestore(target: number | ScrollTarget, onDone?: () => void) {
  if (isTabNavScrollResetPending()) {
    forceWindowTop();
    onDone?.();
    return;
  }
  const normalized: ScrollTarget =
    typeof target === "number" ? { y: target } : { y: target.y || 0, anchor: target.anchor };

  const y = Math.floor(normalized.y || 0);
  const anchor = (normalized.anchor || "").trim();
  if ((y <= 0 && !anchor) || typeof window === "undefined") {
    onDone?.();
    return;
  }
  if (job && job.y === y && job.anchor === anchor) {
    if (onDone) job.onDone = onDone;
    return;
  }
  if (job) {
    job.onDone = undefined;
    finishJob();
  }
  job = {
    y,
    anchor,
    startedAt: performance.now(),
    applied: false,
    ignoreScroll: false,
    onDone,
  };
  ensureResizeWatch();
  if (anchor) observeForAnchor(anchor);
  attachUserGuards();
  if (raf) cancelAnimationFrame(raf);
  raf = requestAnimationFrame(tick);
}

export function cancelScrollRestore() {
  if (job) job.onDone = undefined;
  finishJob();
}

/** @deprecated */
export function scheduleScrollRestore(
  getPendingY: () => number,
  clearPending: () => void,
): () => void {
  requestScrollRestore(getPendingY(), clearPending);
  return () => {
    /* singleton survives React cleanup */
  };
}

export function enableManualScrollRestoration() {
  try {
    if (typeof window !== "undefined" && "scrollRestoration" in window.history) {
      window.history.scrollRestoration = "manual";
    }
  } catch {
    /* ignore */
  }
}

function writeScrollForCurrentPath(y: number, anchor?: string) {
  const path = window.location.pathname || "/";
  try {
    if (path === "/" || path === "") {
      const raw = sessionStorage.getItem(SEARCH_STATE_KEY);
      const parsed = raw ? (JSON.parse(raw) as Record<string, unknown>) : {};
      parsed.y = y;
      if (anchor) parsed.anchor = anchor;
      sessionStorage.setItem(SEARCH_STATE_KEY, JSON.stringify(parsed));
    } else if (path.startsWith("/builder")) {
      let prevAnchor = "";
      try {
        const raw = sessionStorage.getItem(BUILDER_SCROLL_KEY);
        if (raw?.startsWith("{")) {
          const parsed = JSON.parse(raw) as { anchor?: unknown };
          if (typeof parsed.anchor === "string") prevAnchor = parsed.anchor;
        }
      } catch {
        /* ignore */
      }
      sessionStorage.setItem(
        BUILDER_SCROLL_KEY,
        JSON.stringify({ y, anchor: anchor || prevAnchor || "" }),
      );
    } else if (path.startsWith("/collector")) {
      const raw = localStorage.getItem(COLLECTOR_PREFS_KEY);
      const parsed = raw ? (JSON.parse(raw) as Record<string, unknown>) : {};
      parsed.y = y;
      if (anchor) parsed.anchor = anchor;
      localStorage.setItem(COLLECTOR_PREFS_KEY, JSON.stringify(parsed));
    } else if (path.startsWith("/prices")) {
      const raw = localStorage.getItem(PRICES_PREFS_KEY);
      const parsed = raw ? (JSON.parse(raw) as Record<string, unknown>) : {};
      const market =
        parsed.market && typeof parsed.market === "object"
          ? { ...(parsed.market as Record<string, unknown>) }
          : {};
      market.scrollY = y;
      if (anchor) market.scrollAnchor = anchor;
      parsed.market = market;
      localStorage.setItem(PRICES_PREFS_KEY, JSON.stringify(parsed));
    } else if (path.startsWith("/cards/")) {
      sessionStorage.setItem(
        CARD_DETAIL_SCROLL_KEY,
        JSON.stringify({ path, y, anchor: anchor || "" }),
      );
    }
  } catch {
    /* ignore */
  }
}

/**
 * Persist scroll (+ optional card anchor) synchronously before in-app navigation.
 */
export function flushCurrentScroll(anchorId?: string) {
  if (typeof window === "undefined") return;
  // Leaving via a card link ends the tab-switch "pin to top" window.
  tabNavSkipUntil = 0;
  try {
    sessionStorage.removeItem(SKIP_KEY);
  } catch {
    /* ignore */
  }
  const y = Math.max(0, Math.floor(window.scrollY || 0));
  const anchor = (anchorId || "").trim() || undefined;
  writeScrollForCurrentPath(y, anchor);
  window.dispatchEvent(new CustomEvent("opcg:flush-scroll", { detail: { y, anchor } }));
}

/** Clear one-shot card-detail scroll after restore (so a later visit starts at top). */
export function clearCardDetailScroll(pathname?: string) {
  if (typeof window === "undefined") return;
  try {
    const raw = sessionStorage.getItem(CARD_DETAIL_SCROLL_KEY);
    if (!raw) return;
    if (!pathname) {
      sessionStorage.removeItem(CARD_DETAIL_SCROLL_KEY);
      return;
    }
    const parsed = JSON.parse(raw) as { path?: unknown };
    if (typeof parsed.path !== "string" || parsed.path === pathname) {
      sessionStorage.removeItem(CARD_DETAIL_SCROLL_KEY);
    }
  } catch {
    try {
      sessionStorage.removeItem(CARD_DETAIL_SCROLL_KEY);
    } catch {
      /* ignore */
    }
  }
}
