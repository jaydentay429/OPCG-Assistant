const API_ERROR_KEYS: Record<string, string> = {
  "Main deck cannot include Leaders.": "play.deck_no_leaders_in_main",
};

const BANNED_CARD =
  /^Banned card (.+) cannot be included in a deck \(banned from (\d{4}-\d{2}-\d{2})\)\.$/;

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
  if (!banned) return raw;
  const localized = t("play.banned_card", { ids: banned[1], date: banned[2] });
  return localized === "play.banned_card" ? raw : localized;
}

export function localizeBattleApiError(
  message: string,
  t: (key: string, vars?: Record<string, string | number>) => string,
): string {
  const raw = String(message || "").trim();
  if (!raw.includes("Banned card ")) return localizeOne(raw, t);
  return raw
    .split(/(?<=\.)\s+/)
    .map((part) => localizeOne(part, t))
    .join(" ");
}
