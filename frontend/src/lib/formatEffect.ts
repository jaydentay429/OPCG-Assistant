/**
 * Format card effect text for display.
 * Keep stacked prefix tags (timing + once/DON) with the body; only break
 * between separate abilities after sentence / keyword-reminder punctuation.
 */
export function formatEffectLines(text: string): string {
  return String(text || "")
    .replace(/\r\n/g, "\n")
    .trim()
    .replace(/([。．.!！？?）)])\s*(?=[【\[])/g, "$1\n");
}
