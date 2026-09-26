import { displayCardId, normalizeCardId, toBaseCardId } from "./cardId";
import { isParallelArtId } from "./parallelArts";
import type { CardPriceResponse, PriceHistoryPoint } from "./types";

/**
 * Leaders print life in the corner that characters use for cost.
 * The card API copies that printed number into both `life` and `cost`
 * (sampled leaders: ST01-001 5/5, OP13-001 4/4). Characters sometimes
 * also get `life` filled with a copy of `cost` (OP05-093); that is not life.
 */
export function isLeaderCardType(
  cardType?: string | null,
  cardTypeEn?: string | null,
): boolean {
  return /leader|领袖|領袖/i.test(`${cardType || ""} ${cardTypeEn || ""}`);
}

export function leaderLifeValue(card: {
  life?: number | null;
  cost?: number | null;
}): number | null {
  if (typeof card.life === "number" && Number.isFinite(card.life)) return card.life;
  if (typeof card.cost === "number" && Number.isFinite(card.cost)) return card.cost;
  return null;
}

/** Visible stat for the SEO summary and the detail list. */
export function printedCostOrLife(card: {
  card_type?: string | null;
  card_type_en?: string | null;
  cost?: number | null;
  life?: number | null;
}): { kind: "life" | "cost"; value: number } | null {
  if (isLeaderCardType(card.card_type, card.card_type_en)) {
    const value = leaderLifeValue(card);
    return value == null ? null : { kind: "life", value };
  }
  if (typeof card.cost !== "number" || !Number.isFinite(card.cost)) return null;
  return { kind: "cost", value: card.cost };
}

export type CardTitleLang = "zh-Hant" | "zh-Hans" | "en";

/** Suffix written into `<title>` and the H1 when the id ends in `-P` plus digits. */
export function parallelArtSuffix(lang: CardTitleLang = "zh-Hant"): string {
  if (lang === "en") return "(Parallel)";
  if (lang === "zh-Hans") return "(异图卡)";
  return "(異圖卡)";
}

/** Drop a trailing alternate-art suffix so it can be reapplied once for the active id. */
export function stripParallelArtSuffix(name: string): string {
  return String(name || "")
    .replace(/\s*[（(]\s*(?:異圖卡|异图卡)\s*[)）]\s*$/g, "")
    .replace(/\s*(?:異圖卡|异图卡)\s*$/g, "")
    .replace(/\s*\(\s*Parallel\s*\)\s*$/i, "")
    .trim();
}

/**
 * Parallel art is decided by the id (`-P` + digits), not by whatever the name
 * field happens to contain. A name that already ends with the suffix is not
 * given a second one. Reprint ids such as `-R1` are left unchanged.
 */
export function withParallelArtSuffix(
  name: string,
  cardId: string,
  lang: CardTitleLang = "zh-Hant",
): string {
  const label = stripParallelArtSuffix(name);
  if (!isParallelArtId(cardId)) return label;
  const suffix = parallelArtSuffix(lang);
  if (!label) return suffix;
  return lang === "en" ? `${label} ${suffix}` : `${label}${suffix}`;
}

/**
 * Same string `generateMetadata` puts in `<title>`.
 * The parenthetical number stays the base id. `-P` printings add the
 * language's alternate-art suffix on the name.
 */
export function cardDocumentTitle(
  name: string,
  cardId: string,
  lang: CardTitleLang = "zh-Hant",
): string {
  const id = displayCardId(cardId);
  const label = withParallelArtSuffix(name, cardId, lang) || id;
  return `${label}（${id}）| OPCG 卡牌資料`;
}

/** Visible H1. Chinese and English each get their own suffix; `-R` ids do not. */
export function cardHeadingText(
  name: string,
  nameEn: string,
  cardId: string,
  lang: CardTitleLang = "zh-Hant",
): string {
  const id = displayCardId(cardId);
  const zhLang: CardTitleLang = lang === "zh-Hans" ? "zh-Hans" : "zh-Hant";
  const zh = withParallelArtSuffix(name, cardId, zhLang);
  const en = withParallelArtSuffix(nameEn, cardId, "en");
  if (lang === "en") {
    const primary = en || zh || id;
    const secondary = zh && en && zh !== en ? ` / ${zh}` : "";
    return `${primary}${secondary} ${id}`.replace(/\s+/g, " ").trim();
  }
  const primary = zh || en || id;
  const secondary = en && primary !== en ? ` / ${en}` : "";
  return `${primary}${secondary} ${id}`.replace(/\s+/g, " ").trim();
}

/** Id shown on first paint: `pickedVariant`, then `picked`, then the path. */
export function shownCardId(
  cardId: string,
  picked?: string | null,
  pickedVariant?: string | null,
): string {
  const fromPath = normalizeCardId(cardId);
  const fromVariant = normalizeCardId(pickedVariant || "");
  const fromPicked = normalizeCardId(picked || "");
  const candidate = fromVariant || fromPicked || fromPath;
  if (candidate && isSameCardFamily(candidate, fromPath || cardId)) return candidate;
  return fromPath;
}

/** Main image alt. Alternate art names the printing; the base card keeps the card name. */
export function variantMainAlt(name: string, cardId: string): string {
  const id = normalizeCardId(cardId);
  const label = String(name || "").trim() || id;
  if (isParallelArtId(id)) return `${label}（${id}）異畫`;
  return label;
}

/**
 * Thumbnail title and alt. The full catalog id stays in the string so a
 * reprint such as ST01-002-R1 is distinct from the base card (the R1 marker).
 * Alternate art still uses 「卡名（卡號）異畫」.
 */
export function variantThumbAlt(name: string, cardId: string): string {
  const id = normalizeCardId(cardId);
  const label = String(name || "").trim() || id;
  if (isParallelArtId(id)) return `${label}（${id}）異畫`;
  return `${label}（${id}）`;
}

export function cardVariantHref(cardId: string): string {
  return `/cards/${encodeURIComponent(normalizeCardId(cardId))}`;
}

export function cardIdFromPathname(pathname: string): string {
  const match = String(pathname || "").match(/\/cards\/([^/?#]+)/);
  if (!match) return "";
  try {
    return normalizeCardId(decodeURIComponent(match[1]));
  } catch {
    return normalizeCardId(match[1]);
  }
}

/** True when this click should stay a normal link (new tab / window). */
export function shouldDeferVariantClick(event: {
  button?: number;
  metaKey?: boolean;
  ctrlKey?: boolean;
  shiftKey?: boolean;
  altKey?: boolean;
  defaultPrevented?: boolean;
}): boolean {
  const button = event.button ?? 0;
  return Boolean(
    event.defaultPrevented ||
      button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey,
  );
}

export function isSameCardFamily(left: string, right: string): boolean {
  const a = toBaseCardId(left);
  const b = toBaseCardId(right);
  return Boolean(a) && a === b;
}

export function marketPriceToResponse(
  cardId: string,
  raw: Record<string, unknown> | null | undefined,
): CardPriceResponse | null {
  if (!raw || typeof raw !== "object") return null;
  const historyIn = Array.isArray(raw.history) ? raw.history : [];
  const history: PriceHistoryPoint[] = [];
  for (const row of historyIn) {
    if (!row || typeof row !== "object") continue;
    const rec = row as Record<string, unknown>;
    const ts = String(rec.ts || "").trim();
    if (!ts) continue;
    const price = rec.price == null || rec.price === "" ? null : Number(rec.price);
    history.push({
      ts,
      price: price != null && Number.isFinite(price) ? price : null,
    });
  }
  const currentRaw = raw.current_price;
  const current =
    currentRaw == null || currentRaw === "" ? null : Number(currentRaw);
  return {
    card_id: normalizeCardId(cardId) || String(raw.card_id || ""),
    source: String(raw.source || ""),
    currency: String(raw.currency || "JPY"),
    current_price: current != null && Number.isFinite(current) ? current : null,
    last_seen: raw.last_seen == null ? null : String(raw.last_seen),
    last_checked: raw.last_checked == null ? null : String(raw.last_checked),
    history,
    message: raw.message == null ? undefined : String(raw.message),
  };
}
