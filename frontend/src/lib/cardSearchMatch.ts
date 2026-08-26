import * as OpenCC from "opencc-js";
import { displayCardId } from "@/lib/cardId";

const toHans = OpenCC.Converter({ from: "tw", to: "cn" });
const toHant = OpenCC.Converter({ from: "cn", to: "tw" });

/** Mirror backend normalize_name_for_match. */
function normalizeForMatch(text: string): string {
  return String(text || "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "")
    .replace(/[^0-9a-z\u4e00-\u9fffぁ-んァ-ヶー]/gi, "");
}

function safeConvert(text: string, convert: (s: string) => string): string {
  try {
    return convert(text);
  } catch {
    return text;
  }
}

/** Popular Mainland ↔ Taiwan lexical pairs (query-side), beyond pure OpenCC. */
const SYNONYM_PAIRS: [string, string][] = [
  ["路飞", "魯夫"],
  ["路飞", "鲁夫"],
  ["山治", "香吉士"],
  ["乌索普", "騙人布"],
  ["乌索普", "骗人布"],
  ["弗兰奇", "佛朗基"],
  ["甚平", "吉貝爾"],
  ["甚平", "吉贝尔"],
  ["凯多", "海道"],
  ["巴基", "巴其"],
  ["罗罗诺亚", "羅羅亞"],
  ["罗罗诺亚", "罗罗亚"],
  ["托尼托尼", "多尼多尼"],
  ["特拉法尔加", "托拉法爾加"],
  ["特拉法尔加", "托拉法尔加"],
  ["蒙奇", "蒙其"],
  ["草帽海贼团", "草帽一行人"],
  ["草帽海賊團", "草帽一行人"],
  ["红发海贼团", "紅髮海賊團"],
  ["紅发海賊團", "紅髮海賊團"],
];

function expandNameSearchTexts(...parts: Array<string | null | undefined>): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const part of parts) {
    const raw = String(part || "").trim();
    if (!raw) continue;
    for (const v of [raw, safeConvert(raw, toHans), safeConvert(raw, toHant)]) {
      const key = v.trim();
      if (key && !seen.has(key)) {
        seen.add(key);
        out.push(key);
      }
    }
  }
  return out;
}

/** Expand a user query into normalized variants (languages + synonyms). */
export function expandQueryNorms(query: string): string[] {
  const raw = String(query || "").trim();
  if (!raw) return [];
  const variants = expandNameSearchTexts(raw);
  const expanded = [...variants];
  for (const text of variants) {
    for (const [a, b] of SYNONYM_PAIRS) {
      if (a && text.includes(a)) expanded.push(text.split(a).join(b));
      if (b && text.includes(b)) expanded.push(text.split(b).join(a));
    }
  }
  const norms: string[] = [];
  const seen = new Set<string>();
  for (const text of expanded) {
    const norm = normalizeForMatch(text);
    if (norm && !seen.has(norm)) {
      seen.add(norm);
      norms.push(norm);
    }
  }
  return norms;
}

function matchesCardId(cardId: string, query: string): boolean {
  const q = String(query || "").trim();
  if (!q) return true;
  const qLower = q.toLowerCase();
  const cidRaw = String(cardId || "");
  const cidLower = cidRaw.toLowerCase().replace(/_/g, "-");
  const display = displayCardId(cidRaw).toLowerCase();
  const qCompact = qLower.replace(/[-_\s]/g, "");
  const cidCompact = cidLower.replace(/[-_\s]/g, "");
  const displayCompact = display.replace(/[-_\s]/g, "");
  if (display.includes(qLower) || cidLower.includes(qLower)) return true;
  if (qCompact && (cidCompact.includes(qCompact) || displayCompact.includes(qCompact))) return true;
  return false;
}

/**
 * Match collection/binder search against card id, multilingual names, and traits.
 * `searchBlob` should be the backend `search_blob` from deck-stats (pre-normalized).
 */
export function cardMatchesCollectionQuery(
  cardId: string,
  searchBlob: string | null | undefined,
  query: string,
): boolean {
  const q = String(query || "").trim();
  if (!q) return true;
  if (matchesCardId(cardId, q)) return true;
  const blob = String(searchBlob || "");
  if (!blob) return false;
  for (const qn of expandQueryNorms(q)) {
    if (qn && blob.includes(qn)) return true;
  }
  return false;
}
