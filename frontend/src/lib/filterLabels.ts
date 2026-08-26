import type { Lang } from "@/lib/i18n";

type LabelMap = Record<string, { "zh-Hant": string; "zh-Hans": string; en: string }>;

const COLOR_LABELS: LabelMap = {
  Red: { "zh-Hant": "紅", "zh-Hans": "红", en: "Red" },
  Blue: { "zh-Hant": "藍", "zh-Hans": "蓝", en: "Blue" },
  Green: { "zh-Hant": "綠", "zh-Hans": "绿", en: "Green" },
  Purple: { "zh-Hant": "紫", "zh-Hans": "紫", en: "Purple" },
  Black: { "zh-Hant": "黑", "zh-Hans": "黑", en: "Black" },
  Yellow: { "zh-Hant": "黃", "zh-Hans": "黄", en: "Yellow" },
  紅: { "zh-Hant": "紅", "zh-Hans": "红", en: "Red" },
  蓝: { "zh-Hant": "藍", "zh-Hans": "蓝", en: "Blue" },
  藍: { "zh-Hant": "藍", "zh-Hans": "蓝", en: "Blue" },
  绿: { "zh-Hant": "綠", "zh-Hans": "绿", en: "Green" },
  綠: { "zh-Hant": "綠", "zh-Hans": "绿", en: "Green" },
  紫: { "zh-Hant": "紫", "zh-Hans": "紫", en: "Purple" },
  黑: { "zh-Hant": "黑", "zh-Hans": "黑", en: "Black" },
  黄: { "zh-Hant": "黃", "zh-Hans": "黄", en: "Yellow" },
  黃: { "zh-Hant": "黃", "zh-Hans": "黄", en: "Yellow" },
};

const TYPE_LABELS: LabelMap = {
  Leader: { "zh-Hant": "領袖", "zh-Hans": "领袖", en: "Leader" },
  Character: { "zh-Hant": "角色", "zh-Hans": "角色", en: "Character" },
  Event: { "zh-Hant": "事件", "zh-Hans": "事件", en: "Event" },
  Stage: { "zh-Hant": "舞台", "zh-Hans": "舞台", en: "Stage" },
  Don: { "zh-Hant": "咚卡", "zh-Hans": "咚卡", en: "DON card" },
  領袖: { "zh-Hant": "領袖", "zh-Hans": "领袖", en: "Leader" },
  领袖: { "zh-Hant": "領袖", "zh-Hans": "领袖", en: "Leader" },
  角色: { "zh-Hant": "角色", "zh-Hans": "角色", en: "Character" },
  角色卡: { "zh-Hant": "角色", "zh-Hans": "角色", en: "Character" },
  事件: { "zh-Hant": "事件", "zh-Hans": "事件", en: "Event" },
  舞台: { "zh-Hant": "舞台", "zh-Hans": "舞台", en: "Stage" },
  咚卡: { "zh-Hant": "咚卡", "zh-Hans": "咚卡", en: "DON card" },
};

const ATTR_LABELS: LabelMap = {
  Slash: { "zh-Hant": "斬", "zh-Hans": "斩", en: "Slash" },
  Strike: { "zh-Hant": "打", "zh-Hans": "打", en: "Strike" },
  Ranged: { "zh-Hant": "射", "zh-Hans": "射", en: "Ranged" },
  Special: { "zh-Hant": "特", "zh-Hans": "特", en: "Special" },
  Wisdom: { "zh-Hant": "知", "zh-Hans": "知", en: "Wisdom" },
  Unknown: { "zh-Hant": "？", "zh-Hans": "？", en: "Unknown" },
  斬: { "zh-Hant": "斬", "zh-Hans": "斩", en: "Slash" },
  斩: { "zh-Hant": "斬", "zh-Hans": "斩", en: "Slash" },
  打: { "zh-Hant": "打", "zh-Hans": "打", en: "Strike" },
  射: { "zh-Hant": "射", "zh-Hans": "射", en: "Ranged" },
  特: { "zh-Hant": "特", "zh-Hans": "特", en: "Special" },
  知: { "zh-Hant": "知", "zh-Hans": "知", en: "Wisdom" },
};

const KEYWORD_LABELS: LabelMap = {
  blocker: { "zh-Hant": "防禦", "zh-Hans": "防御", en: "Blocker" },
  rush: { "zh-Hant": "速攻", "zh-Hans": "速攻", en: "Rush" },
  double_attack: { "zh-Hant": "雙重攻擊", "zh-Hans": "双重攻击", en: "Double Attack" },
  banish: { "zh-Hant": "流放", "zh-Hans": "流放", en: "Banish" },
  blockerless: { "zh-Hant": "不可阻擋", "zh-Hans": "不可阻挡", en: "Blockerless" },
  trigger: { "zh-Hant": "觸發器", "zh-Hans": "触发器", en: "Trigger" },
  don_x1: { "zh-Hant": "咚×1", "zh-Hans": "咚×1", en: "DON!! ×1" },
  don_x2: { "zh-Hant": "咚×2", "zh-Hans": "咚×2", en: "DON!! ×2" },
  don_x3: { "zh-Hant": "咚×3+", "zh-Hans": "咚×3+", en: "DON!! ×3+" },
};

/** Fixed order shown in the Effects filter dropdown. */
export const FILTER_KEYWORD_IDS = [
  "blocker",
  "rush",
  "double_attack",
  "banish",
  "blockerless",
  "trigger",
  "don_x1",
  "don_x2",
  "don_x3",
] as const;

const RARITY_LABELS: LabelMap = {
  "GOLD DON": { "zh-Hant": "Gold DON", "zh-Hans": "Gold DON", en: "Gold DON" },
  "Gold DON": { "zh-Hant": "Gold DON", "zh-Hans": "Gold DON", en: "Gold DON" },
  "DON-SP": { "zh-Hant": "Gold DON", "zh-Hans": "Gold DON", en: "Gold DON" },
  DON: { "zh-Hant": "DON", "zh-Hans": "DON", en: "DON" },
  "DON-P": { "zh-Hant": "DON", "zh-Hans": "DON", en: "DON" },
  SP: { "zh-Hant": "SP", "zh-Hans": "SP", en: "SP" },
  SP卡: { "zh-Hant": "SP", "zh-Hans": "SP", en: "SP" },
};

function pick(map: LabelMap, raw: string, lang: Lang): string | null {
  const key = String(raw || "").trim();
  if (!key) return null;
  const hit = map[key] || map[key.replace(/^./, (c) => c.toUpperCase())] || map[key.toUpperCase()];
  if (!hit) return null;
  return hit[lang] || hit.en;
}

/** Display label for filter/detail tokens. Values sent to API stay English. */
export function localizeFilterToken(
  kind: "color" | "type" | "attr" | "keyword" | "rarity" | "generic",
  raw: string,
  lang: Lang,
): string {
  const text = String(raw || "").trim();
  if (!text) return "";
  if (kind === "color") return pick(COLOR_LABELS, text, lang) || text;
  if (kind === "type") return pick(TYPE_LABELS, text, lang) || text;
  if (kind === "attr") return pick(ATTR_LABELS, text, lang) || text;
  if (kind === "keyword") return pick(KEYWORD_LABELS, text, lang) || text;
  if (kind === "rarity") return pick(RARITY_LABELS, text, lang) || text;
  return text;
}

export function localizeFilterTokens(
  kind: "color" | "type" | "attr" | "keyword" | "rarity",
  items: string[] | null | undefined,
  lang: Lang,
): string[] {
  if (!items?.length) return [];
  return items.map((x) => localizeFilterToken(kind, x, lang));
}

export function filterGroupValueKind(
  groupKey: string,
): "color" | "type" | "attr" | "keyword" | "rarity" | "generic" {
  if (groupKey === "colors") return "color";
  if (groupKey === "card_types") return "type";
  if (groupKey === "attributes") return "attr";
  if (groupKey === "keywords") return "keyword";
  if (groupKey === "rarities") return "rarity";
  return "generic";
}
