/**
 * Layout listens for this event without importing the OpenCC loader, so the
 * dictionary chunks stay out of the shared first-load graph.
 */
export const OPENCC_READY_EVENT = "opcg-opencc-ready";
