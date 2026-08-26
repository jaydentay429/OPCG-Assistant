import type { DeckStatFields } from "@/lib/api";
import type { Lang } from "@/lib/i18n";

export type CurveBucket = { key: string; n: number };

function toInt(v: unknown): number | null {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? Math.floor(n) : null;
}

function typeKey(raw: unknown): string {
  const s = String(raw || "").trim();
  if (!s) return "?";
  if (/leader|领袖|領袖/i.test(s)) return "Leader";
  if (/character|角色/i.test(s)) return "Character";
  if (/event|事件/i.test(s)) return "Event";
  if (/stage|舞台|场地|場地/i.test(s)) return "Stage";
  return s;
}

/** Event/Stage with missing stats are printed 0, not unknown. Leaders stay off the curve. */
export function costBucketKey(cost: number | null, cardType?: unknown): string {
  if (cost === null) {
    const tk = typeKey(cardType);
    if (tk === "Event" || tk === "Stage") return "0";
    return "?";
  }
  return String(Math.min(10, Math.max(0, cost)));
}

function costLabel(key: string, lang: Lang): string {
  if (key === "?") return lang === "en" ? "?" : "？";
  if (key === "10+") return "10";
  return key;
}

/** Printed character power only. No cap, no "?" — missing power is omitted. */
export function powerBucketKey(power: number | null, cardType?: unknown): string | null {
  if (power == null || !Number.isFinite(power) || power <= 0) return null;
  const tk = typeKey(cardType);
  if (tk === "Event" || tk === "Stage" || tk === "Leader") return null;
  return `${Math.floor(power / 1000)}k`;
}

/** Printed character Counter only. Leaders / Events / Stages omitted. */
export function counterBucketKey(counter: number | null, cardType?: unknown): string | null {
  const tk = typeKey(cardType);
  if (tk === "Event" || tk === "Stage" || tk === "Leader") return null;
  const n = counter == null || !Number.isFinite(counter) ? 0 : Math.floor(counter);
  if (n <= 0) return "0";
  if (n % 1000 === 0) return `+${n / 1000}k`;
  return `+${n}`;
}

function counterKeyNum(key: string): number {
  if (key === "0") return 0;
  const k = key.replace(/^\+/, "");
  const m = /^(\d+)k$/.exec(k);
  if (m) return Number(m[1]) * 1000;
  return Number.parseInt(k, 10) || 0;
}

export function orderedCounterKeys(bucket: Record<string, number>): string[] {
  return Object.keys(bucket)
    .filter((k) => (bucket[k] || 0) > 0)
    .sort((a, b) => counterKeyNum(a) - counterKeyNum(b));
}

function powerKeyNum(key: string): number {
  const m = /^(\d+)k$/.exec(key);
  if (m) return Number(m[1]);
  if (key === "0") return 0;
  return Number.parseInt(key, 10) || 0;
}

export function orderedPowerKeys(bucket: Record<string, number>, _fillGaps = false): string[] {
  return Object.keys(bucket)
    .filter((k) => k !== "?" && k !== "12k+" && (bucket[k] || 0) > 0)
    .sort((a, b) => powerKeyNum(a) - powerKeyNum(b));
}

function bump(map: Record<string, number>, key: string, n: number) {
  map[key] = (map[key] || 0) + n;
}

/** Live deck structure summary for the builder (cost curve + types). */
export function summarizeDeckStructure(
  leader: string | null,
  cards: Record<string, number>,
  statsMap: Record<string, DeckStatFields>,
  lang: Lang,
): { costCurve: CurveBucket[]; powerCurve: CurveBucket[]; counterCurve: CurveBucket[]; types: CurveBucket[] } {
  const costBucket: Record<string, number> = {};
  const powerBucket: Record<string, number> = {};
  const counterBucket: Record<string, number> = {};
  const typeCounts: Record<string, number> = {};

  if (leader) {
    bump(typeCounts, "Leader", 1);
  }

  for (const [id, rawQty] of Object.entries(cards)) {
    const n = Math.max(0, Math.floor(Number(rawQty) || 0));
    if (!n) continue;
    const st = statsMap[id] || {};
    const cost = toInt(st.cost);
    const costKey = costBucketKey(cost, st.card_type);
    bump(costBucket, costKey, n);
    const powerKey = powerBucketKey(toInt(st.power), st.card_type);
    if (powerKey) bump(powerBucket, powerKey, n);
    const counterKey = counterBucketKey(toInt(st.counter), st.card_type);
    if (counterKey) bump(counterBucket, counterKey, n);
    bump(typeCounts, typeKey(st.card_type), n);
  }

  const costCurve: CurveBucket[] = [];
  for (let c = 0; c <= 10; c++) {
    const n = (costBucket[String(c)] || 0) + (c === 10 ? costBucket["10+"] || 0 : 0);
    if (n > 0) costCurve.push({ key: costLabel(String(c), lang), n });
  }
  if (costBucket["?"]) costCurve.push({ key: costLabel("?", lang), n: costBucket["?"] });

  const powerCurve: CurveBucket[] = orderedPowerKeys(powerBucket).map((key) => ({
    key,
    n: powerBucket[key] || 0,
  }));

  const counterCurve: CurveBucket[] = orderedCounterKeys(counterBucket).map((key) => ({
    key,
    n: counterBucket[key] || 0,
  }));

  const types = Object.entries(typeCounts)
    .filter(([, n]) => n > 0)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([key, n]) => ({ key, n }));

  return { costCurve, powerCurve, counterCurve, types };
}
