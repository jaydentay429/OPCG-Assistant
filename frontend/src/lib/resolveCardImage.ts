import { cardImageHash, CARD_IMAGE_MANIFEST } from "./cardImageManifest";
import { normalizeCardId, toBaseCardId } from "./cardId";
import { isParallelArtId } from "./parallelArts";

/** Public card-art host. Share and sitemap URLs stay on this host. */
export const CARD_SHARE_IMAGE_HOST = "https://img.optcgassistant.com";

export type CardImageInput = {
  id?: string | null;
  card_id?: string | null;
  /** Gate for step ①. The share URL is built from the id and the manifest hash, not from this string. */
  img_url?: string | null;
};

export type ResolveCardImageOptions = {
  /**
   * id → 8-hex content hash. Tests pass a fixture. Production uses the build manifest.
   * Do not read a live CDN listing from here.
   */
  hashes?: Readonly<Record<string, string>>;
};

export type ResolvedCardImage = {
  url: string;
  alt: string;
  /** `base` is the card's own PNG. `parallel` is the first `-P1`, `-P2`, … file. */
  kind: "base" | "parallel";
  id: string;
};

const HASH_RE = /^[0-9a-f]{8}$/;

function cardKey(card: CardImageInput): string {
  return normalizeCardId(String(card.id || card.card_id || ""));
}

function hasPrintedImageUrl(card: CardImageInput): boolean {
  return String(card.img_url || "").trim() !== "";
}

function hashFor(id: string, hashes: Readonly<Record<string, string>> | undefined): string {
  if (!hashes) return cardImageHash(id);
  const hash = hashes[id] || hashes[id.toLowerCase()] || "";
  return HASH_RE.test(hash) ? hash : "";
}

function publicPngUrl(id: string, hash: string): string {
  return `${CARD_SHARE_IMAGE_HOST}/${encodeURIComponent(id)}.png?h=${hash}`;
}

function parallelNumber(id: string): number {
  return Number(id.match(/-P(\d+)$/)?.[1] || 0);
}

let manifestParallels: Map<string, readonly string[]> | null = null;

/** Base id → `-P1`, `-P2`, … that have a valid hash, numeric order. */
function parallelsByBase(hashes: Readonly<Record<string, string>> | undefined): Map<string, readonly string[]> {
  if (!hashes && manifestParallels) return manifestParallels;
  const source = hashes || CARD_IMAGE_MANIFEST;
  const groups = new Map<string, string[]>();
  const seen = new Set<string>();
  for (const raw of Object.keys(source)) {
    const id = normalizeCardId(raw);
    if (!id || seen.has(id) || !isParallelArtId(id)) continue;
    if (!hashFor(id, hashes)) continue;
    seen.add(id);
    const base = toBaseCardId(id);
    const list = groups.get(base);
    if (list) list.push(id);
    else groups.set(base, [id]);
  }
  for (const list of groups.values()) {
    list.sort((a, b) => parallelNumber(a) - parallelNumber(b) || a.localeCompare(b));
  }
  const frozen = new Map<string, readonly string[]>();
  for (const [base, list] of groups) frozen.set(base, list);
  if (!hashes) manifestParallels = frozen;
  return frozen;
}

/**
 * Share image for one card, in order:
 * ① its own PNG when `img_url` is non-empty and the manifest has a hash;
 * ② otherwise the first same-number alternate (`-P1`, `-P2`, …) with a hash;
 * ③ otherwise null.
 */
export function resolveCardImage(
  card: CardImageInput | null | undefined,
  options?: ResolveCardImageOptions,
): ResolvedCardImage | null {
  if (!card) return null;
  const id = cardKey(card);
  if (!id) return null;
  const hashes = options?.hashes;

  if (hasPrintedImageUrl(card)) {
    const own = hashFor(id, hashes);
    if (own) {
      return { url: publicPngUrl(id, own), alt: id, kind: "base", id };
    }
  }

  const base = toBaseCardId(id);
  for (const parallelId of parallelsByBase(hashes).get(base) || []) {
    const hash = hashFor(parallelId, hashes);
    if (!hash) continue;
    return { url: publicPngUrl(parallelId, hash), alt: parallelId, kind: "parallel", id: parallelId };
  }
  return null;
}

/**
 * Sitemap `<image:loc>`. Only step ①. An empty `img_url`, or a hash that
 * exists only on an alternate, does not emit `<image:image>`.
 */
export function sitemapCardImageLoc(
  card: CardImageInput | null | undefined,
  options?: ResolveCardImageOptions,
): string | null {
  const resolved = resolveCardImage(card, options);
  if (resolved?.kind !== "base") return null;
  return resolved.url;
}
