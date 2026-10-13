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

/**
 * Pull a trigger line out of effect text when the trigger field is empty.
 * OpenCC tw2s turns 【觸發器】 into 【触发器】; 【触发】 is the shorter
 * simplified label used in some copy. A mid-line 「持有【触发器】」 is a
 * card property, not a timing, so the marker has to start the line.
 */
const TRIGGER_LINE =
  /(?:^|\n)\s*((?:【觸發器】|【触发器】|【触发】|\[Trigger\])[^\n]*)/;

export function splitEffectTrigger(
  effect: string,
  trigger: string,
): { body: string; trigger: string } {
  const effectText = String(effect || "").trim();
  let triggerText = String(trigger || "").trim();
  if (!triggerText) {
    const match = effectText.match(TRIGGER_LINE);
    if (match) triggerText = match[1].trim();
  }
  let body = effectText;
  if (triggerText && body.includes(triggerText)) {
    body = body.replace(triggerText, "").replace(/\n{2,}/g, "\n").trim();
  }
  return { body: formatEffectLines(body), trigger: triggerText };
}
