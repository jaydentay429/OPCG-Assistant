#!/usr/bin/env node
/**
 * Write src/generated/card-ids.json and set-index.json so sitemap + /sets pages
 * work in production standalone (no access to repo-level index/).
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const candidates = [
  process.env.OPCG_CARDS_JSON,
  join(frontendRoot, "..", "index", "cards_by_id.json"),
  join(frontendRoot, "index", "cards_by_id.json"),
  join("/Users/jayden/Documents/OPCG_Project/index/cards_by_id.json"),
  join("/opt/opcg/app/index/cards_by_id.json"),
].filter(Boolean);

function setCodeFromCardId(cardId) {
  const id = String(cardId || "")
    .trim()
    .toUpperCase()
    .replace(/_/g, "-");
  if (!id) return null;
  if (id.startsWith("DON")) return "DON";
  if (/^P-\d{3}/.test(id)) return "P";
  const m = id.match(/^([A-Z]{2,4}\d{0,2})-\d{3}/);
  return m ? m[1] : null;
}

function setSortKey(code) {
  const m = String(code).match(/^([A-Z]+)(\d*)$/);
  if (!m) return `z-${code}`;
  const family = m[1];
  const n = m[2] ? Number(m[2]) : 0;
  const famRank = family === "OP" ? "0" : family === "EB" ? "1" : family === "ST" ? "2" : family === "P" ? "8" : "9";
  return `${famRank}-${family}-${String(n).padStart(4, "0")}`;
}

let raw = null;
let source = "";
for (const file of candidates) {
  try {
    if (!existsSync(file)) continue;
    const parsed = JSON.parse(readFileSync(file, "utf8"));
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      raw = parsed;
      source = file;
      break;
    }
  } catch (err) {
    console.warn(`[generate-card-ids] skip ${file}: ${err instanceof Error ? err.message : err}`);
  }
}

const destDir = join(frontendRoot, "src", "generated");
mkdirSync(destDir, { recursive: true });

const ids = raw ? Object.keys(raw).filter(Boolean).sort() : [];
writeFileSync(join(destDir, "card-ids.json"), `${JSON.stringify(ids)}\n`);
console.log(`[generate-card-ids] ${ids.length} ids from ${source || "(none)"}`);

const grouped = new Map();
if (raw) {
  for (const id of ids) {
    const code = setCodeFromCardId(id);
    if (!code) continue;
    const row = raw[id] || {};
    const name = String(row.name || id).trim() || id;
    if (!grouped.has(code)) grouped.set(code, []);
    grouped.get(code).push({ id, name });
  }
}

const sets = [...grouped.entries()]
  .sort((a, b) => setSortKey(a[0]).localeCompare(setSortKey(b[0])))
  .map(([code, cards]) => ({
    code,
    count: cards.length,
    cards,
  }));

writeFileSync(join(destDir, "set-index.json"), `${JSON.stringify(sets)}\n`);
console.log(`[generate-card-ids] ${sets.length} sets`);
if (!ids.length) {
  console.warn("[generate-card-ids] wrote empty list — sitemap will omit /cards/{id}");
}
