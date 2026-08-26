import * as OpenCC from "opencc-js";
import type { Lang } from "@/lib/i18n";
import { HANS_PHRASE_FIXES } from "@/locales/hansPhraseFixes.generated";
import NAME_ALIASES from "@/locales/nameAliases.generated";
import NAME_HANS_BY_EN from "@/locales/nameHansByEn.generated";

const toHans = OpenCC.Converter({ from: "tw", to: "cn" });

const CJK_RE = /[\u4e00-\u9fff]/;

function normalizeEnName(raw: string): string {
  return String(raw || "")
    .trim()
    .replace(/\s*\(Parallel\)\s*$/i, "")
    .replace(/\s+/g, " ");
}

function stripAltArtLabel(text: string): string {
  return String(text || "")
    .replace(/[（(]?\s*異圖卡\s*[)）]?/g, "")
    .replace(/[（(]?\s*异图卡\s*[)）]?/g, "")
    .replace(/\s*\(\s*Parallel\s*\)\s*/gi, "")
    .trim();
}

function applyHansPhraseFixes(text: string): string {
  let out = text;
  for (const [from, to] of HANS_PHRASE_FIXES) {
    if (!from || from === to) continue;
    out = out.split(from).join(to);
  }
  return out;
}

/** Taiwan spoken names applied when English map misses a card. Longest first. */
const HANT_NAME_FIXES: [string, string][] = [
  ["艾德華・紐蓋特", "白鬍子"],
  ["馬歇爾・D・汀奇", "黑鬍子"],
  ["喬拉可爾・密佛格", "鷹眼・密佛格"],
  ["唐吉訶德・多佛朗明哥", "多佛朗明哥"],
  ["巴索羅繆・大熊", "大熊"],
  ["夏洛特・莉莉", "大媽"],
  ["波特卡斯・D・艾斯", "艾斯"],
  ["蒙其・D・魯夫", "魯夫"],
  ["蒙其・D・卡普", "卡普"],
  ["羅羅亞・索隆", "索隆"],
  ["多尼多尼・喬巴", "喬巴"],
  ["妮可・羅賓", "羅賓"],
  ["托拉法爾加・羅", "羅"],
  ["波雅・漢考克", "女帝・漢考克"],
  ["波爾薩利諾", "黃猿"],
  ["月光・摩利亞", "摩利亞"],
  ["尤斯塔斯・基德", "基德"],
  ["珠寶・波妮", "波妮"],
  ["羅布・路基", "路基"],
  ["斯摩格", "煙鬼"],
  ["荒卷", "綠牛"],
  ["庫山", "青雉"],
  ["一笑", "藤虎"],
  ["海道", "凱多"],
  ["盃", "赤犬"],
  ["矢龍", "希留"],
  ["矢龙", "希留"],
];

function applyHantNameFixes(text: string): string {
  let out = text;
  for (const [from, to] of HANT_NAME_FIXES) {
    if (!from || from === to) continue;
    out = out.split(from).join(to);
  }
  return out;
}

/** True if the string contains CJK ideographs. */
export function hasCjk(text: string | null | undefined): boolean {
  return CJK_RE.test(String(text || ""));
}

/**
 * Prefer the English half of bilingual engine strings like
 * "Choose target / 選擇目標" or drop CJK-only text in English UI.
 */
export function preferLangText(text: string | null | undefined, lang: Lang): string {
  const raw = String(text || "").trim();
  if (!raw) return "";
  if (lang !== "en") return raw;
  if (!hasCjk(raw)) return raw;
  const parts = raw.split(/\s*\/\s*/).map((p) => p.trim()).filter(Boolean);
  if (parts.length >= 2) {
    const enPart = parts.find((p) => !hasCjk(p));
    if (enPart) return enPart;
  }
  return "";
}

/** Convert Taiwan Traditional card text into Mainland Simplified + popular name fixes. */
export function toSimplifiedText(text: string | null | undefined): string {
  if (!text) return "";
  return applyHansPhraseFixes(toHans(String(text)));
}

/**
 * Localize a card/character name.
 * - zh-Hant: Taiwan spoken names (赤犬/黃猿/魯夫…) with official fallback
 * - zh-Hans: full English→Mainland map (1133+), fallback OpenCC+phrase fixes
 * - en: prefer nameEn; never fall back to CJK (caller should use card id)
 */
export function localizeCardName(
  name: string | null | undefined,
  nameEn: string | null | undefined,
  lang: Lang,
): string {
  if (lang === "en") {
    const en = stripAltArtLabel(normalizeEnName(nameEn || ""));
    if (en) return en;
    const original = stripAltArtLabel(String(name || "").trim());
    if (original && !hasCjk(original)) return original;
    return "";
  }

  const original = String(name || "").trim();
  const fallbackEn = stripAltArtLabel(String(nameEn || "").trim());
  if (!original) return fallbackEn;

  const enKey = normalizeEnName(nameEn || "");
  const alias = enKey ? NAME_ALIASES[enKey] : undefined;

  // Chinese UI: always prefer a real CJK official name. Never let stale EN→EN
  // map entries (common for new sets) replace 洛基/嘉蘭/… with Loki/Gloriosa.
  if (lang === "zh-Hant") {
    if (alias?.display_hant && hasCjk(alias.display_hant)) {
      return stripAltArtLabel(alias.display_hant);
    }
    if (hasCjk(original)) return stripAltArtLabel(applyHantNameFixes(original));
    return stripAltArtLabel(original);
  }

  // zh-Hans: prefer English→Mainland map first. Taiwan paper names often differ
  // (Shanks=傑克, Kaido=海道); OpenCC alone would yield 杰克/海道.
  if (alias?.display_hans && hasCjk(alias.display_hans)) {
    return stripAltArtLabel(alias.display_hans);
  }
  const fromMap = enKey ? NAME_HANS_BY_EN[enKey] : undefined;
  if (fromMap && hasCjk(fromMap)) return stripAltArtLabel(fromMap);
  if (hasCjk(original)) {
    return stripAltArtLabel(toSimplifiedText(original));
  }
  return stripAltArtLabel(original || fallbackEn);
}

/**
 * Localize card effect / trigger / summary text.
 * For English, pass textEn when available; CJK-only strings are omitted.
 */
export function localizeCardText(
  text: string | null | undefined,
  lang: Lang,
  textEn?: string | null,
): string {
  if (lang === "en") {
    const en = String(textEn || "").trim();
    if (en) return en;
    return preferLangText(text, "en");
  }
  if (!text) return "";
  if (lang !== "zh-Hans") return String(text);
  return toSimplifiedText(text);
}

export function localizeCardList(
  items: string[] | null | undefined,
  lang: Lang,
  itemsEn?: string[] | null,
): string[] {
  if (lang === "en") {
    if (itemsEn?.length) return itemsEn.map((x) => String(x || "").trim()).filter(Boolean);
    if (!items?.length) return [];
    return items.map((x) => preferLangText(x, "en")).filter(Boolean);
  }
  if (!items?.length) return [];
  if (lang !== "zh-Hans") return items;
  return items.map((x) => toSimplifiedText(x));
}

/** Official EN product titles keyed by set code (OP-01, ST-13, …). */
const SET_CODE_EN: Record<string, string> = {
  "OP-01": "ROMANCE DAWN",
  "OP-02": "Paramount War",
  "OP-03": "Pillars of Strength",
  "OP-04": "Kingdoms of Intrigue",
  "OP-05": "Awakening of the New Era",
  "OP-06": "Wings of the Captain",
  "OP-07": "500 Years in the Future",
  "OP-08": "Two Legends",
  "OP-09": "Emperors in the New World",
  "OP-10": "Royal Blood",
  "OP-11": "A Fist of Divine Speed",
  "OP-12": "Legacy of the Master",
  "OP-13": "Carrying on His Will",
  "OP-14": "The Azure Sea's Seven",
  "OP-15": "Adventure on Kami's Island",
  "OP-16": "The Time of Battle",
  "OP-17": "The World's Strongest Warriors",
  "OP-18": "Booster Pack OP-18",
  "EB-01": "Memorial Collection",
  "EB-02": "Anime 25th collection",
  "EB-03": "ONE PIECE Heroines Edition",
  "EB-04": "EGGHEAD CRISIS",
  "EB-05": "EXTRA BOOSTER EB-05",
  "PRB-01": "ONE PIECE CARD THE BEST",
  "PRB-02": "ONE PIECE CARD THE BEST vol.2",
  "ST-01": "Straw Hat Crew",
  "ST-02": "Worst Generation",
  "ST-03": "The Seven Warlords of the Sea",
  "ST-04": "Animal Kingdom Pirates",
  "ST-05": "ONE PIECE FILM edition",
  "ST-06": "Navy",
  "ST-07": "Big Mom Pirates",
  "ST-08": "Side Monkey.D.Luffy",
  "ST-09": "Side Yamato",
  "ST-10": "The Three Captains",
  "ST-11": "Side Uta",
  "ST-12": "Zoro & Sanji",
  "ST-13": "Ultra Deck: The Three Brothers",
  "ST-14": "3D2Y",
  "ST-15": "Red Edward.Newgate",
  "ST-16": "Green Uta",
  "ST-17": "Blue Donquixote Doflamingo",
  "ST-18": "Purple Monkey.D.Luffy",
  "ST-19": "Black Smoker",
  "ST-20": "Yellow Charlotte Katakuri",
  "ST-21": "GEAR5",
  "ST-22": "Ace & Newgate",
  "ST-23": "Red Shanks",
  "ST-24": "Green Jewelry.Bonney",
  "ST-25": "Blue Buggy",
  "ST-26": "Purple/Black Monkey.D.Luffy",
  "ST-27": "Black Marshall.D.Teach",
  "ST-28": "Green/Yellow Yamato",
  "ST-29": "EGGHEAD",
  "ST-30": "Starter Deck EX Luffy & Ace",
  "ST-31": "Starter Deck Red Monkey.D.Luffy",
  "ST-32": "Starter Deck Green Roronoa Zoro",
  "ST-33": "Starter Deck Blue Kuzan",
  "ST-34": "Starter Deck Purple Charlotte Katakuri",
  "ST-35": "Starter Deck Red/Black Sabo",
  "ST-36": "Starter Deck Yellow Eustass.Kid",
  "AC-01": "Treasure Collection vol.1 Vinsmoke Reiju",
  "TS-01": "Mini Tin Set VOL.1",
  "TS-02": "Mini Tin Set vol.2",
};

/** Exact Traditional Chinese (and mixed) source → English. */
const CARD_SOURCE_EN: Record<string, string> = {
  通用咚卡: "Generic DON!!",
  家庭牌組套裝: "Family Deck Set",
  友誼交流會: "Friendship Meetup",
  啟航活動推廣卡包: "Launch Event Promotion Pack",
  補充包贈禮活動: "Booster Pack Gift Campaign",
  娜美編號卡獲取活動: "Nami Serial Card Campaign",
  魯夫編號卡獲取活動: "Luffy Serial Card Campaign",
  主題推廣包: "Theme Promotion Pack",
  "主題推廣包 ver.新四皇": "Theme Promotion Pack ver. New Four Emperors",
  推廣卡套組: "Promotion Card Set",
  推廣卡套組2026: "Promotion Card Set 2026",
  推廣卡包A: "Promotion Pack A",
  推廣卡包B: "Promotion Pack B",
  "ONE PIECE卡片對戰 推廣卡包2022": "ONE PIECE Card Game Promotion Pack 2022",
  "ONE PIECE卡片對戰 推廣卡包2022 Vol.2": "ONE PIECE Card Game Promotion Pack 2022 Vol.2",
  "ONE PIECE卡牌對戰 安可卡包": "ONE PIECE Card Game Encore Pack",
  "ONE PIECE卡牌對戰 寶藏箱 vol.1": "ONE PIECE Card Game Treasure Box vol.1",
  "ONE PIECE卡牌對戰 SOUND LOADER Volume.1 特典卡":
    "ONE PIECE Card Game SOUND LOADER Volume.1 Promo Card",
  "ONE PIECE卡牌對戰 SOUND LOADER Volume.2 特典卡":
    "ONE PIECE Card Game SOUND LOADER Volume.2 Promo Card",
  "3周年！ONE PIECE卡牌秘寶活動卡包": "3rd Anniversary! ONE PIECE Card Treasure Event Pack",
  "高級補充包 ONE PIECE CARD THE BEST 收藏盒套裝":
    "Premium Booster ONE PIECE CARD THE BEST Collector's Box Set",
  "官方遊戲墊板 納菲魯塔利・薇薇": "Official Playmat Nefertari Vivi",
  "官方遊戲墊板 限定版 VOL.3": "Official Playmat Limited Edition VOL.3",
  "官方遊戲墊板 限定版 vol.4": "Official Playmat Limited Edition vol.4",
  亞洲錦標賽套裝2022: "Asia Championship Set 2022",
  "亞洲錦標賽2022預賽高名次獎品": "Asia Championship 2022 Preliminary High Placement Prize",
  "亞洲錦標賽2022香港地區決賽冠軍": "Asia Championship 2022 Hong Kong Regional Finals Champion",
  "冠軍錦標賽套裝2023 (前四皇)": "Championship Set 2023 (Former Four Emperors)",
  "冠軍錦標賽套裝2023 (艾斯・薩波・魯夫)": "Championship Set 2023 (Ace / Sabo / Luffy)",
  "珍藏系列 vol.1 賓什莫克・麗珠【AC-01】": "Treasure Collection vol.1 Vinsmoke Reiju【AC-01】",
};

const SOURCE_PHRASE_EN: [string, string][] = [
  ["特規大獎賽高名次紀念品", "Special Grand Prix High Placement Souvenir"],
  ["特規大獎賽優勝紀念品", "Special Grand Prix Winner Souvenir"],
  ["旗艦戰高名次紀念品", "Flagship Battle High Placement Souvenir"],
  ["旗艦戰前8名紀念品", "Flagship Battle Top 8 Souvenir"],
  ["旗艦戰優勝紀念品", "Flagship Battle Winner Souvenir"],
  ["常規賽亞洲特例紀念品", "Standard Battle Asia Special Souvenir"],
  ["交流會亞洲特例紀念品", "Meetup Asia Special Souvenir"],
  ["常規賽優勝紀念品", "Standard Battle Winner Souvenir"],
  ["交流會紀念品", "Meetup Souvenir"],
  ["到場紀念品", "Attendance Souvenir"],
  ["常規賽卡包", "Standard Battle Pack"],
  ["推廣卡包 EX", "Promotion Pack EX"],
  ["推廣卡包", "Promotion Pack"],
  ["起始牌組EX", "Starter Deck EX"],
  ["起始牌組", "Starter Deck"],
  ["補充包", "Booster Pack"],
  ["8包現開賽優勝紀念品", "8-Pack Sealed Winner Souvenir"],
  ["整盒購買特典", "Case Purchase Bonus"],
  ["發售特典", "Release Bonus"],
  ["冠軍錦標賽套裝", "Championship Set"],
  ["冠軍錦標賽", "Championship"],
  ["亞洲錦標賽", "Asia Championship"],
  ["區域決賽", "Regional Finals"],
  ["區域預賽", "Regional Preliminary"],
  ["第一次預賽", "First Preliminary"],
  ["高名次獎品", "High Placement Prize"],
  ["高名次紀念品", "High Placement Souvenir"],
  ["前16名獎品", "Top 16 Prize"],
  ["前8名紀念品", "Top 8 Souvenir"],
  ["前6名獎品", "Top 6 Prize"],
  ["前4名紀念品", "Top 4 Souvenir"],
  ["前3名獎品", "Top 3 Prize"],
  ["前2名獎品", "Top 2 Prize"],
  ["核心活動", "Core Event"],
  ["開催記念品", "Event Souvenir"],
  ["交流会", "Meetup"],
  ["應募者全員大サービス", "Applicant All Service"],
  ["応募者全員大サービス", "Applicant All Service"],
  ["應募者全員サービス", "Applicant All Service"],
  ["応募者全員サービス", "Applicant All Service"],
  ["特典卡", "Promo Card"],
  ["特典", "Bonus"],
  ["付録", "Bonus"],
  ["紀念品", "Souvenir"],
  ["獎品", "Prize"],
  ["優勝", "Winner"],
];

const SOURCE_CHAR_EN: [string, string][] = [
  ["蒙其・D・魯夫", "Monkey.D.Luffy"],
  ["蒙其・D・卡普", "Monkey.D.Garp"],
  ["夏洛特・卡塔克利", "Charlotte Katakuri"],
  ["唐吉訶德・多佛朗明哥", "Donquixote Doflamingo"],
  ["艾德華・紐蓋特", "Edward.Newgate"],
  ["馬歇爾・D・汀奇", "Marshall.D.Teach"],
  ["羅羅亞・索隆", "Roronoa Zoro"],
  ["尤斯塔斯・基德", "Eustass.Kid"],
  ["珠寶・波妮", "Jewelry.Bonney"],
  ["賓什莫克・麗珠", "Vinsmoke Reiju"],
  ["納菲魯塔利・薇薇", "Nefertari Vivi"],
  ["波特卡斯・D・艾斯", "Portgas.D.Ace"],
  ["紐蓋特", "Newgate"],
  ["美音", "Uta"],
  ["大和", "Yamato"],
  ["薩波", "Sabo"],
  ["艾斯", "Ace"],
  ["庫山", "Kuzan"],
  ["斯摩格", "Smoker"],
  ["巴其", "Buggy"],
  ["傑克", "Shanks"],
];

const SOURCE_COLOR_EN: [string, string][] = [
  ["紫黑", "Purple/Black"],
  ["紅黑", "Red/Black"],
  ["綠黃", "Green/Yellow"],
  ["紅", "Red"],
  ["綠", "Green"],
  ["藍", "Blue"],
  ["紫", "Purple"],
  ["黃", "Yellow"],
  ["黑", "Black"],
];

const MONTH_EN = [
  "",
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

function extractSetCode(raw: string): string | null {
  const text = String(raw || "");
  const m = text.match(/【\s*([A-Z]{1,4}-\d{2})\s*】/i) || text.match(/\[\s*([A-Z]{1,4}-\d{2})\s*\]/i);
  if (!m) return null;
  return m[1].toUpperCase();
}

function localizeSourceEn(raw: string): string {
  const text = String(raw || "").trim();
  if (!text) return "";
  if (CARD_SOURCE_EN[text]) return CARD_SOURCE_EN[text];
  if (!hasCjk(text)) return text;

  const code = extractSetCode(text);
  if (code && SET_CODE_EN[code]) {
    return `${SET_CODE_EN[code]}【${code}】`;
  }

  let out = text;
  // "2024年11月…" → "Nov 2024 …"
  out = out.replace(/(\d{4})\s*年\s*(\d{1,2})\s*月/g, (_, y, m) => {
    const mi = Number(m);
    const mon = MONTH_EN[mi] || m;
    return `${mon} ${y}`;
  });
  out = out.replace(/(\d{4})\s*年/g, "$1 ");

  // Year can sit between event type and souvenir suffix.
  out = out.replace(/常規賽\s+/g, "Standard Battle ");
  out = out.replace(/旗艦戰\s+/g, "Flagship Battle ");
  out = out.replace(/交流會\s+/g, "Meetup ");
  out = out.replace(/交流会\s+/g, "Meetup ");

  for (const [from, to] of SOURCE_PHRASE_EN) {
    if (out.includes(from)) out = out.split(from).join(to);
  }
  for (const [from, to] of SOURCE_CHAR_EN) {
    if (out.includes(from)) out = out.split(from).join(to);
  }
  for (const [from, to] of SOURCE_COLOR_EN) {
    out = out.replace(new RegExp(`${from}(?=[\\s・]|$)`, "g"), to);
  }

  out = out.replace(/\s+/g, " ").trim();
  if (hasCjk(out) && code) return `【${code}】`;
  return preferLangText(out, "en") || out;
}

/**
 * Localize DON!! card names.
 * Index stores Traditional Chinese + English after sync; this also cleans leftovers.
 */
export function localizeDonCardName(
  name: string | null | undefined,
  nameEn: string | null | undefined,
  lang: Lang,
): string {
  if (lang === "en") {
    const en = stripAltArtLabel(normalizeEnName(nameEn || ""));
    if (en) return en;
    const original = stripAltArtLabel(String(name || "").trim());
    if (original && !hasCjk(original)) return original;
    // Fallback: keep "DON!! Card (...)" shape if Chinese name exists.
    const zh = String(name || "").trim();
    if (zh.startsWith("咚卡")) {
      const rest = zh.replace(/^咚卡[・‧·]?/, "").trim();
      return rest ? `DON!! Card (${rest})` : "DON!! Card";
    }
    return "DON!! Card";
  }

  const localized = localizeCardName(name, nameEn, lang);
  if (localized) return localized;
  return lang === "zh-Hans" ? "咚卡" : "咚卡";
}

/** Localize card source / pack labels for detail UI. */
export function localizeCardSources(sources: string[] | null | undefined, lang: Lang): string[] {
  const rows = (sources || []).map((x) => String(x || "").trim()).filter(Boolean);
  if (!rows.length) return [];
  if (lang === "en") return rows.map((x) => localizeSourceEn(x));
  if (lang === "zh-Hans") return rows.map((x) => toSimplifiedText(x));
  return rows;
}

/** Localize DON source labels (pack / generic). */
export function localizeDonSources(sources: string[] | null | undefined, lang: Lang): string[] {
  return localizeCardSources(sources, lang);
}
