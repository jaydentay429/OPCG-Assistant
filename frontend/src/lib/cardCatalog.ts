import fs from "fs";
import path from "path";
import type { Card } from "./types";

/**
 * Decide whether a card lookup that did not return a card is a real miss.
 * 404/422 (or a successful empty body) for an id the catalog does not know
 * is a 404. Anything else — timeouts, 5xx, or a 404 for a catalogued id —
 * must stay an error so a blip is not published as "this card does not exist".
 */
export function missingCardShould404(status: number | null, knownInCatalog: boolean): boolean {
  const definitiveMiss = status == null || status === 404 || status === 422;
  if (!definitiveMiss) return false;
  if (knownInCatalog) return false;
  return true;
}

/** Match the API's normalize_card_id so catalog membership uses the stored key. */
export function normalizeCatalogCardId(raw: string): string {
  let cleaned = String(raw || "")
    .trim()
    .toUpperCase()
    .replace(/_/g, "-")
    .replace(/ /g, "")
    .replace(/－/g, "-");
  cleaned = cleaned.replace(/[^A-Z0-9-]/g, "");
  const don = cleaned.match(/^(DON[A-Z0-9]*)-(\d{3,5}(?:-[A-Z0-9]+)?)$/);
  if (don) return `${don[1]}-${don[2]}`;
  const standard = cleaned.match(/^([A-Z]{2,4})-?(\d{2})-(\d{3}(?:-[A-Z0-9]+)?)$/);
  if (standard) return `${standard[1]}${standard[2]}-${standard[3]}`;
  return cleaned;
}

type CatalogCache = {
  file: string;
  mtimeMs: number;
  ids: Set<string>;
  records: Record<string, unknown>;
};

let catalogCache: CatalogCache | null = null;
let resolvedFile: string | null = null;
let warnedMissing = false;

function catalogCandidates(): string[] {
  const cwd = process.cwd();
  return [
    path.join(cwd, "..", "index", "cards_by_id.json"),
    path.join(cwd, "index", "cards_by_id.json"),
    path.join(cwd, "..", "..", "index", "cards_by_id.json"),
    path.join(cwd, "..", "..", "..", "index", "cards_by_id.json"),
  ];
}

function resolveCatalogFile(): string | null {
  if (resolvedFile) {
    try {
      if (fs.existsSync(resolvedFile)) return resolvedFile;
    } catch {
      /* rescan */
    }
    resolvedFile = null;
    catalogCache = null;
  }
  for (const file of catalogCandidates()) {
    try {
      if (fs.existsSync(file)) {
        resolvedFile = file;
        return file;
      }
    } catch {
      /* try the next candidate */
    }
  }
  return null;
}

function loadCatalog(): CatalogCache | null {
  const file = resolveCatalogFile();
  if (!file) {
    if (!warnedMissing) {
      warnedMissing = true;
      console.warn(
        "[cards] index/cards_by_id.json was not found; card 404s will trust the API response only",
      );
    }
    return null;
  }
  const mtimeMs = fs.statSync(file).mtimeMs;
  if (catalogCache && catalogCache.file === file && catalogCache.mtimeMs === mtimeMs) {
    return catalogCache;
  }
  const raw = JSON.parse(fs.readFileSync(file, "utf8")) as Record<string, unknown>;
  const records = raw && typeof raw === "object" ? raw : {};
  const ids = new Set(Object.keys(records));
  catalogCache = { file, mtimeMs, ids, records };
  return catalogCache;
}

function asOptionalString(value: unknown): string | null | undefined {
  if (value == null) return value === null ? null : undefined;
  return String(value);
}

function asOptionalNumber(value: unknown): number | null | undefined {
  if (value == null) return value === null ? null : undefined;
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value);
  return undefined;
}

function asStringList(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) return undefined;
  return value.map((item) => String(item ?? "")).filter((item) => item.length > 0);
}

/** Map one index row onto the card payload the page already renders. */
export function cardFromCatalogRecord(cardId: string, raw: Record<string, unknown>): Card {
  const cardType = asOptionalString(raw.card_type) || asOptionalString(raw.category) || null;
  const cardTypeEn = asOptionalString(raw.card_type_en) || asOptionalString(raw.category_en) || null;
  return {
    id: cardId,
    name: asOptionalString(raw.name),
    name_en: asOptionalString(raw.name_en),
    rarity: asOptionalString(raw.rarity),
    colors: asStringList(raw.colors),
    colors_en: asStringList(raw.colors_en),
    pack_id: asOptionalString(raw.pack_id),
    img_url: asOptionalString(raw.img_url),
    img_full_url: asOptionalString(raw.img_full_url),
    cost: asOptionalNumber(raw.cost),
    effect: asOptionalString(raw.effect),
    effect_en: asOptionalString(raw.effect_en),
    trigger: asOptionalString(raw.trigger),
    trigger_en: asOptionalString(raw.trigger_en),
    power: asOptionalNumber(raw.power),
    traits: asStringList(raw.traits),
    traits_en: asStringList(raw.traits_en),
    card_type: cardType,
    card_type_en: cardTypeEn,
    counter: asOptionalNumber(raw.counter),
    block_number: asOptionalNumber(raw.block_number),
    attributes: asStringList(raw.attributes),
    attributes_en: asStringList(raw.attributes_en),
    card_sets: asStringList(raw.card_sets),
    life: asOptionalNumber(raw.life),
  };
}

/** True when the on-disk card index contains this id. False if the index cannot be read. */
export function catalogHasCard(cardId: string): boolean {
  try {
    const catalog = loadCatalog();
    if (!catalog) return false;
    return catalog.ids.has(normalizeCatalogCardId(cardId));
  } catch (error) {
    console.warn("[cards] failed to read card catalog", error);
    return false;
  }
}

/**
 * One card from the bundled index, or null when the id or the file is missing.
 * This is a local read, not another API call.
 */
export function catalogCard(cardId: string): Card | null {
  try {
    const catalog = loadCatalog();
    if (!catalog) return null;
    const key = normalizeCatalogCardId(cardId);
    const raw = catalog.records[key];
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
    return cardFromCatalogRecord(key, raw as Record<string, unknown>);
  } catch (error) {
    console.warn("[cards] failed to read bundled card", error);
    return null;
  }
}
