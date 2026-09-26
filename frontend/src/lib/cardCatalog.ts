import fs from "fs";
import path from "path";

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

function loadCatalogIds(): Set<string> | null {
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
    return catalogCache.ids;
  }
  const raw = JSON.parse(fs.readFileSync(file, "utf8")) as Record<string, unknown>;
  const ids = new Set(Object.keys(raw));
  catalogCache = { file, mtimeMs, ids };
  return ids;
}

/** True when the on-disk card index contains this id. False if the index cannot be read. */
export function catalogHasCard(cardId: string): boolean {
  try {
    const ids = loadCatalogIds();
    if (!ids) return false;
    return ids.has(normalizeCatalogCardId(cardId));
  } catch (error) {
    console.warn("[cards] failed to read card catalog", error);
    return false;
  }
}
