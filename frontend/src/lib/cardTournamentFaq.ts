/** Fields used to render one tournament row in the card FAQ. */
export type TournamentFaqAppearance = {
  meta_title?: string | null;
  format?: string | null;
  leader_name?: string | null;
  leader?: string | null;
};

/** Same display string the card FAQ joins into the tournament answer. */
export function tournamentFaqLabel(row: TournamentFaqAppearance): string {
  const meta = row.meta_title || row.format || "賽事";
  const leader = row.leader_name || row.leader || "";
  return leader ? `${meta}（${leader}）` : meta;
}

/**
 * Up to `limit` tournament labels, in first-seen order.
 * Rows whose displayed text matches an earlier label after trimming whitespace
 * are dropped, including when the upstream rows differ by date or deck id.
 */
export function uniqueTournamentFaqLabels(
  rows: readonly TournamentFaqAppearance[],
  limit = 3,
): string[] {
  const seen = new Set<string>();
  const labels: string[] = [];
  const cap = Math.max(0, limit);
  for (const row of rows.slice(0, cap)) {
    const label = tournamentFaqLabel(row);
    const key = label.trim();
    if (seen.has(key)) continue;
    seen.add(key);
    labels.push(label);
  }
  return labels;
}

/** Answer sentence for「常見於哪些賽事卡組」. */
export function tournamentFaqAnswer(
  rows: readonly TournamentFaqAppearance[],
  limit = 3,
): string {
  return `本站公開賽事資料中出現於：${uniqueTournamentFaqLabels(rows, limit).join("、")}。`;
}
