import { normalizeCardId, toBaseCardId } from "./cardId";

/**
 * Public site origin. Hardcoded on purpose: the app sits behind Caddy, so
 * request.url / nextUrl / the Host header are localhost:3000 and must never
 * be used to build a canonical or og:url.
 */
export const CARD_PAGE_ORIGIN = "https://optcgassistant.com";

const PLACEHOLDER = new Set(["-", "—", "－", "–"]);

/**
 * Alternate art (異畫) is a catalog id whose base, from the existing
 * `toBaseCardId` rules, is followed by `-P` and digits only:
 *   OP05-093-P1, ST18-005-P2, P-084-P1
 * Reprint suffixes such as -R1 / -R2 are not alternate art.
 * DON illustrated ids (DON17-10163) and promo bases (P-084) are not either.
 */
export function isParallelArtId(cardId: string): boolean {
  const id = normalizeCardId(cardId);
  if (!id) return false;
  const base = toBaseCardId(id);
  if (!base || base === id) return false;
  return /^-P\d+$/.test(id.slice(base.length));
}

/** Absolute canonical URL. Alternate-art ids point at the base card. */
export function cardCanonicalUrl(cardId: string): string {
  const id = normalizeCardId(cardId);
  const target = isParallelArtId(id) ? toBaseCardId(id) : id;
  return `${CARD_PAGE_ORIGIN}/cards/${encodeURIComponent(target)}`;
}

/** Sitemap card ids: drop alternate-art (`-P<digits>`) urls, keep everything else. */
export function sitemapCardIds(ids: readonly string[]): string[] {
  return ids.filter((id) => Boolean(id) && !isParallelArtId(id));
}

/** Other `-P` printings of the same base, numeric order, excluding `cardId` itself. */
export function parallelArtIdsAmong(cardId: string, catalogIds: readonly string[]): string[] {
  const id = normalizeCardId(cardId);
  const base = toBaseCardId(id);
  const out: string[] = [];
  for (const raw of catalogIds) {
    const other = normalizeCardId(raw);
    if (!other || other === id || !isParallelArtId(other)) continue;
    if (toBaseCardId(other) !== base) continue;
    out.push(other);
  }
  out.sort((a, b) => {
    const na = Number(a.match(/-P(\d+)$/)?.[1] || 0);
    const nb = Number(b.match(/-P(\d+)$/)?.[1] || 0);
    return na - nb || a.localeCompare(b);
  });
  return out;
}

export function presentMetaText(value: string | null | undefined): string {
  const text = String(value || "").trim();
  if (!text || PLACEHOLDER.has(text)) return "";
  return text;
}

/**
 * Card meta description. Placeholder dashes are omitted so a missing series,
 * rarity, or type cannot render as 「系列 -」 / 「稀有度 -」 / 「類型 -」.
 */
export function cardMetaDescription(input: {
  name: string;
  id: string;
  series?: string | null;
  rarity?: string | null;
  cardType?: string | null;
  effect?: string | null;
}): string {
  const name = presentMetaText(input.name) || input.id;
  const series = presentMetaText(input.series);
  const rarity = presentMetaText(input.rarity);
  const cardType = presentMetaText(input.cardType);
  const effect = String(input.effect || "");
  const visibleEffect = presentMetaText(effect);
  const parts = [
    series ? `系列 ${series}` : "",
    rarity ? `稀有度 ${rarity}` : "",
    cardType ? `類型 ${cardType}` : "",
  ].filter(Boolean);
  const detail = parts.length ? `，${parts.join("，")}` : "";
  const effectSnippet = visibleEffect.replace(/\s+/g, " ").slice(0, 110);
  const effectBit = visibleEffect
    ? `效果：${effectSnippet}${effect.length > 110 ? "…" : ""}`
    : "";
  return `${name}（${input.id}）是《ONE PIECE 卡牌對戰》卡牌${detail}。${effectBit}`;
}
