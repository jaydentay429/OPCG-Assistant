const API_ERROR_KEYS: Record<string, string> = {
  "Main deck cannot include Leaders.": "play.deck_no_leaders_in_main",
};

const BANNED_CARD =
  /^Banned card (.+) cannot be included in a deck \(banned from (\d{4}-\d{2}-\d{2})\)\.$/;

/** Battle routes emit the English sentence. Deck save emits the simplified one. */
const BANNED_PAIR_EN =
  /^Banned pair (.+?) and (.+?) cannot be in the same deck \(from (\d{4}-\d{2}-\d{2})\)\.$/;
const BANNED_PAIR_HANS =
  /^禁用组合 (.+?) 与 (.+?) 不能放在同一套卡组（(\d{4}-\d{2}-\d{2}) 起）。$/;
const BANNED_PAIR_HANT =
  /^禁用組合 (.+?) 與 (.+?) 不能放在同一套卡組（(\d{4}-\d{2}-\d{2}) 起）。$/;

const SENTENCE_SPLIT = ["Banned card ", "Banned pair ", "禁用组合 ", "禁用組合 "];

function localizePair(
  match: RegExpExecArray,
  t: (key: string, vars?: Record<string, string | number>) => string,
): string {
  const localized = t("play.banned_pair", { a: match[1], b: match[2], date: match[3] });
  return localized === "play.banned_pair" ? match[0] : localized;
}

function localizeOne(
  raw: string,
  t: (key: string, vars?: Record<string, string | number>) => string,
): string {
  const key = API_ERROR_KEYS[raw];
  if (key) {
    const localized = t(key);
    return localized === key ? raw : localized;
  }
  const banned = BANNED_CARD.exec(raw);
  if (banned) {
    const localized = t("play.banned_card", { ids: banned[1], date: banned[2] });
    return localized === "play.banned_card" ? raw : localized;
  }
  const pair = BANNED_PAIR_EN.exec(raw) || BANNED_PAIR_HANS.exec(raw) || BANNED_PAIR_HANT.exec(raw);
  if (!pair) return raw;
  return localizePair(pair, t);
}

export function localizeBattleApiError(
  message: string,
  t: (key: string, vars?: Record<string, string | number>) => string,
): string {
  const raw = String(message || "").trim();
  if (!SENTENCE_SPLIT.some((mark) => raw.includes(mark))) return localizeOne(raw, t);
  return raw
    .split(/(?<=[.。])\s+/)
    .map((part) => localizeOne(part, t))
    .join(" ");
}
