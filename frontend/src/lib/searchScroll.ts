/** Pager clicks should move; reduced motion stays an instant jump. */
export function searchResultsScrollBehavior(reducedMotion: boolean): ScrollBehavior {
  return reducedMotion ? "auto" : "smooth";
}

/**
 * Document scroll offset that places the results block just under a sticky bar.
 * `elementTop` is the block's viewport-relative top (`getBoundingClientRect().top`).
 */
export function searchResultsScrollTop(
  elementTop: number,
  windowScrollY: number,
  stickyHeight: number,
): number {
  const sticky = Number.isFinite(stickyHeight) && stickyHeight > 0 ? stickyHeight : 0;
  const y = windowScrollY + elementTop - sticky;
  if (!Number.isFinite(y)) return 0;
  return Math.max(0, y);
}
