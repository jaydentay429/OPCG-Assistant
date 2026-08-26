#!/usr/bin/env node
/**
 * Regenerate Mainland Simplified name map from Taiwan card index.
 *
 * Usage (from frontend/):
 *   node scripts/generate-hans-names.mjs
 *
 * Requires: ../index/cards_by_id.json and opencc-js installed.
 */
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { createRequire } from "module";

const require = createRequire(import.meta.url);
const OpenCC = require("opencc-js");

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "../..");
const INDEX = path.join(ROOT, "index/cards_by_id.json");
const OUT_MAP = path.join(__dirname, "../src/locales/nameHansByEn.generated.ts");
const OUT_FIXES = path.join(__dirname, "../src/locales/hansPhraseFixes.generated.ts");
const OUT_JSON = path.join(ROOT, "meta/name_hans_by_en.json");
const ALIAS_JSON = path.join(ROOT, "meta/name_aliases.json");
const OUT_ALIASES_TS = path.join(__dirname, "../src/locales/nameAliases.generated.ts");

const toHans = OpenCC.Converter({ from: "tw", to: "cn" });

const FIXES = [
  ["蒙其・D・鲁夫", "蒙奇・D・路飞"],
  ["蒙其・D・多拉格", "蒙奇・D・龙"],
  ["蒙其・D・卡普", "蒙奇・D・卡普"],
  ["罗罗亚・索隆", "罗罗诺亚・索隆"],
  ["多尼多尼・乔巴", "托尼托尼・乔巴"],
  ["托拉法尔加・罗", "特拉法尔加・罗"],
  ["唐吉诃德・多佛朗明哥", "唐吉诃德・多弗拉门戈"],
  ["乔拉可尔・密佛格", "鹰眼米霍克"],
  ["夏洛特・卡塔克利", "夏洛特・卡塔库栗"],
  ["波雅・汉考克", "波雅・汉库克"],
  ["巴索罗缪・大熊", "巴索罗米・熊"],
  ["罗布・路基", "罗布・路奇"],
  ["贝卡帕库", "贝加庞克"],
  ["宾什莫克・香吉士", "文斯莫克・山治"],
  ["娜菲鲁塔利・薇薇", "奈菲特丽・薇薇"],
  ["纳菲鲁塔利・薇薇", "奈菲特丽・薇薇"],
  ["艾波利欧・伊万科夫", "艾斯巴古・伊万科夫"],
  ["亚尔丽塔", "阿尔维达"],
  ["恶龙", "阿龙"],
  ["达丝琪", "达斯琪"],
  ["罗罗亚", "罗罗诺亚"],
  ["骗人布", "乌索普"],
  ["香吉士", "山治"],
  ["佛朗基", "弗兰奇"],
  ["吉贝尔", "甚平"],
  ["巴其", "巴基"],
  ["海道", "凯多"],
  ["密佛格", "米霍克"],
  ["多拉格", "龙"],
  ["路基", "路奇"],
  ["鲁夫", "路飞"],
  ["鲁西", "路西"],
];

const EN_OVERRIDES = {
  Sakazuki: "赤犬",
  Borsalino: "黄猿",
  Kuzan: "青雉",
  Issho: "藤虎",
  Aramaki: "绿牛",
  Shanks: "香克斯",
  Jack: "杰克",
  Jinbe: "甚平",
  Lucy: "路西",
  "Monkey.D.Luffy": "蒙奇・D・路飞",
  "Monkey.D.Garp": "蒙奇・D・卡普",
  "Monkey.D.Dragon": "蒙奇・D・龙",
  "Roronoa Zoro": "罗罗诺亚・索隆",
  Usopp: "乌索普",
  Sanji: "山治",
  "Vinsmoke Sanji": "文斯莫克・山治",
  "Tony Tony.Chopper": "托尼托尼・乔巴",
  Franky: "弗兰奇",
  "General Franky": "弗兰奇将军",
  Kaido: "凯多",
  Buggy: "巴基",
  "Dracule Mihawk": "鹰眼米霍克",
  "Donquixote Doflamingo": "唐吉诃德・多弗拉门戈",
  "Charlotte Katakuri": "夏洛特・卡塔库栗",
  "Trafalgar Law": "特拉法尔加・罗",
  "Rob Lucci": "罗布・路奇",
  Vegapunk: "贝加庞克",
  "Bartholomew Kuma": "巴索罗米・熊",
  "Boa Hancock": "波雅・汉库克",
};

function convertName(tw) {
  let s = toHans(String(tw || ""));
  for (const [from, to] of FIXES) {
    if (from && from !== to) s = s.split(from).join(to);
  }
  return s;
}

function normalizeEn(en) {
  return String(en || "")
    .trim()
    .replace(/\s*\(Parallel\)\s*$/i, "")
    .replace(/\s+/g, " ");
}

let aliasMap = {};
if (fs.existsSync(ALIAS_JSON)) {
  aliasMap = JSON.parse(fs.readFileSync(ALIAS_JSON, "utf8")) || {};
}
for (const [en, row] of Object.entries(aliasMap)) {
  if (row && typeof row === "object" && row.display_hans) {
    EN_OVERRIDES[en] = row.display_hans;
  }
}

const aliasTs = [
  "/** Auto-generated from meta/name_aliases.json */",
  "export type NameAliasRow = {",
  "  display_hans?: string;",
  "  display_hant?: string;",
  "  aliases?: string[];",
  "};",
  "const NAME_ALIASES: Record<string, NameAliasRow> = " + JSON.stringify(aliasMap, null, 2) + ";",
  "",
  "export default NAME_ALIASES;",
  "",
];
fs.writeFileSync(OUT_ALIASES_TS, aliasTs.join("\n"));

const data = JSON.parse(fs.readFileSync(INDEX, "utf8"));
const byEn = {};
for (const v of Object.values(data)) {
  if (!v || typeof v !== "object") continue;
  const en = normalizeEn(v.name_en);
  const zh = String(v.name || "").trim();
  if (!en || !zh) continue;
  if (!byEn[en]) byEn[en] = zh;
}

const CJK_RE = /[\u4e00-\u9fff]/;
const out = {};
for (const [en, tw] of Object.entries(byEn)) {
  const converted = EN_OVERRIDES[en] || convertName(tw);
  // Never persist English→English placeholders; let runtime fall back to OpenCC(name).
  if (!CJK_RE.test(converted) && CJK_RE.test(tw)) continue;
  if (!CJK_RE.test(converted) && converted === en) continue;
  out[en] = converted;
}

const mapLines = [
  "/**",
  " * Auto-generated: all unique English card names → Mainland Simplified Chinese.",
  " * Regenerate: node scripts/generate-hans-names.mjs",
  " */",
  "const NAME_HANS_BY_EN: Record<string, string> = {",
];
for (const en of Object.keys(out).sort((a, b) => a.localeCompare(b))) {
  mapLines.push(`  ${JSON.stringify(en)}: ${JSON.stringify(out[en])},`);
}
mapLines.push("};", "", "export default NAME_HANS_BY_EN;", "");
fs.writeFileSync(OUT_MAP, mapLines.join("\n"));

const fixLines = [
  "/** Shared phrase fixes applied after OpenCC for effects/traits/fallback names. */",
  "export const HANS_PHRASE_FIXES: [string, string][] = [",
];
for (const [a, b] of FIXES) {
  if (a !== b) fixLines.push(`  [${JSON.stringify(a)}, ${JSON.stringify(b)}],`);
}
fixLines.push("];", "");
fs.writeFileSync(OUT_FIXES, fixLines.join("\n"));

fs.mkdirSync(path.dirname(OUT_JSON), { recursive: true });
fs.writeFileSync(OUT_JSON, `${JSON.stringify(out, null, 0)}\n`);

console.log(`Wrote ${Object.keys(out).length} names → ${path.relative(process.cwd(), OUT_MAP)}`);
console.log(`Wrote JSON → ${path.relative(process.cwd(), OUT_JSON)}`);
