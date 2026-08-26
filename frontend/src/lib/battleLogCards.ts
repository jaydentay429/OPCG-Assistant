import type { BattleLogEntry } from "./battleWs";

/** OPCG card id e.g. OP14-094, ST01-001, OP01-001-P1 */
export const BATTLE_CARD_ID_RE = /[A-Z]{2,4}\d{2}-\d{2,4}(?:-[A-Z0-9]+)*/gi;
export const BATTLE_CARD_ID_ONE = /^[A-Z]{2,4}\d{2}-\d{2,4}(?:-[A-Z0-9]+)*$/i;

export function collectCardIdsFromLogs(log: Array<string | BattleLogEntry> | undefined | null): string[] {
  const ids = new Set<string>();
  const addRaw = (raw: unknown) => {
    const s = String(raw ?? "").trim();
    if (!s) return;
    if (BATTLE_CARD_ID_ONE.test(s)) {
      ids.add(s);
      return;
    }
    for (const part of s.split(/[,，、\s]+/)) {
      const p = part.trim();
      if (BATTLE_CARD_ID_ONE.test(p)) ids.add(p);
    }
    const matches = s.match(BATTLE_CARD_ID_RE);
    if (matches) for (const m of matches) ids.add(m);
  };
  for (const entry of log || []) {
    if (typeof entry === "string") {
      addRaw(entry);
      continue;
    }
    if (entry.id != null) addRaw(entry.id);
    if (entry.ids != null) addRaw(entry.ids);
  }
  return [...ids];
}
