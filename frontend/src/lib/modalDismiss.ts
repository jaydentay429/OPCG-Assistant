/** Ignore backdrop clicks for this long after the dialog opens. Close and Esc stay immediate. */
export const BACKDROP_DISMISS_GRACE_MS = 400;

export function shouldIgnoreBackdropDismiss(
  openedAt: number,
  now: number,
  graceMs = BACKDROP_DISMISS_GRACE_MS,
): boolean {
  return now - openedAt < graceMs;
}
