import type { Lang } from "@/lib/i18n";
import { normalizeCardId, toBaseCardId } from "@/lib/cardId";
import { convertToHansSync } from "@/lib/openccLazy";
import en from "@/locales/en";
import zhHans from "@/locales/zh-Hans";
import zhHant from "@/locales/zh-Hant";
import restrictionDocument from "../../../index/official_restriction_list.json" with { type: "json" };

export type RestrictionKind = "banned" | "restricted" | "pair";

export type RestrictionEntry = {
  card_id?: string;
  card_ids?: string[];
  type: RestrictionKind;
  effective_date: string;
  source_url: string;
  asia_effective_date?: string;
  asia_source_url?: string;
};

type RestrictionDocument = {
  current_list_urls: string[];
  entries: RestrictionEntry[];
};

const documentData = restrictionDocument as RestrictionDocument;

const DICTS: Record<Lang, Record<string, string>> = {
  en,
  "zh-Hans": zhHans,
  "zh-Hant": zhHant,
};

export const RESTRICTION_ENTRIES: RestrictionEntry[] = documentData.entries;
export const RESTRICTION_LIST_URLS: string[] = documentData.current_list_urls;

function fill(template: string, vars?: Record<string, string | number>): string {
  let text = template;
  if (!vars) return text;
  for (const [key, value] of Object.entries(vars)) {
    text = text.replaceAll(`{${key}}`, String(value));
  }
  return text;
}

/** Traditional is the source. Simplified uses OpenCC when it is loaded, otherwise the zh-Hans dictionary. */
export function restrictionPhrase(
  lang: Lang,
  key: string,
  vars?: Record<string, string | number>,
): string {
  if (lang === "zh-Hans") {
    const traditional = zhHant[key];
    if (traditional) {
      const converted = convertToHansSync(fill(traditional, vars));
      if (converted != null) return converted;
    }
  }
  const template = DICTS[lang][key] || (lang === "zh-Hans" ? zhHant[key] : "") || en[key] || key;
  return fill(template, vars);
}

export function restrictionBaseId(cardId: string): string {
  return toBaseCardId(normalizeCardId(cardId));
}

function entryIds(entry: RestrictionEntry): string[] {
  if (entry.type === "pair") return (entry.card_ids || []).map((id) => restrictionBaseId(id));
  return entry.card_id ? [restrictionBaseId(entry.card_id)] : [];
}

export function cardRestriction(cardId: string): RestrictionEntry | null {
  const base = restrictionBaseId(cardId);
  if (!base) return null;
  return (
    RESTRICTION_ENTRIES.find((entry) => entry.type !== "pair" && entryIds(entry)[0] === base) ?? null
  );
}

export function bannedBadgeText(cardId: string, lang: Lang): string | null {
  const entry = cardRestriction(cardId);
  if (!entry || entry.type !== "banned") return null;
  return restrictionPhrase(lang, "detail.banned_from", { date: entry.effective_date });
}

export function restrictedBadgeText(cardId: string, lang: Lang): string | null {
  const entry = cardRestriction(cardId);
  if (!entry || entry.type !== "restricted") return null;
  return restrictionPhrase(lang, "detail.restricted_from", { date: entry.effective_date });
}

function todayIso(now = new Date()): string {
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export type DeckRestrictionWarning = {
  kind: RestrictionKind;
  effectiveDate: string;
  ids: string[];
  text: string;
};

function presentBases(
  leaderId: string | null | undefined,
  cards: Record<string, number> | null | undefined,
): Map<string, string[]> {
  const present = new Map<string, string[]>();
  const add = (raw: string, qty: number) => {
    if (qty <= 0) return;
    const actual = normalizeCardId(raw);
    if (!actual) return;
    const base = restrictionBaseId(actual);
    const bucket = present.get(base) ?? [];
    if (!bucket.includes(actual)) bucket.push(actual);
    present.set(base, bucket);
  };
  if (leaderId) add(leaderId, 1);
  for (const [raw, qty] of Object.entries(cards || {})) add(raw, Number(qty) || 0);
  return present;
}

export function deckRestrictionWarnings(
  leaderId: string | null | undefined,
  cards: Record<string, number> | null | undefined,
  lang: Lang,
  onDate = todayIso(),
  entries: RestrictionEntry[] = RESTRICTION_ENTRIES,
): DeckRestrictionWarning[] {
  const present = presentBases(leaderId, cards);
  const counts = new Map<string, number>();
  const leaderActual = leaderId ? normalizeCardId(leaderId) : "";
  if (leaderActual) counts.set(restrictionBaseId(leaderActual), 1);
  for (const [raw, qty] of Object.entries(cards || {})) {
    const count = Number(qty) || 0;
    if (count <= 0) continue;
    const actual = normalizeCardId(raw);
    if (!actual || actual === leaderActual) continue;
    const base = restrictionBaseId(actual);
    counts.set(base, (counts.get(base) || 0) + count);
  }

  const warnings: DeckRestrictionWarning[] = [];
  for (const entry of entries) {
    if (entry.effective_date > onDate) continue;
    const ids = entryIds(entry);
    if (entry.type === "banned" || entry.type === "restricted") {
      const base = ids[0];
      if (!base || !present.has(base)) continue;
      if (entry.type === "restricted" && (counts.get(base) || 0) <= 1) continue;
      const shown = [...(present.get(base) || [])].sort();
      const key = entry.type === "banned" ? "deck.warn_banned" : "deck.warn_restricted";
      warnings.push({
        kind: entry.type,
        effectiveDate: entry.effective_date,
        ids: shown,
        text: restrictionPhrase(lang, key, { id: shown.join(", "), date: entry.effective_date }),
      });
      continue;
    }
    const [left, right] = ids;
    if (!left || !right || !present.has(left) || !present.has(right)) continue;
    const leftIds = [...(present.get(left) || [])].sort();
    const rightIds = [...(present.get(right) || [])].sort();
    warnings.push({
      kind: "pair",
      effectiveDate: entry.effective_date,
      ids: [...leftIds, ...rightIds],
      text: restrictionPhrase(lang, "deck.warn_pair", {
        a: leftIds.join(", "),
        b: rightIds.join(", "),
        date: entry.effective_date,
      }),
    });
  }
  return warnings;
}
