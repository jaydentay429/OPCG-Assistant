const API_ERROR_KEYS: Record<string, string> = {
  "Main deck cannot include Leaders.": "play.deck_no_leaders_in_main",
};

export function localizeBattleApiError(
  message: string,
  t: (key: string, vars?: Record<string, string | number>) => string,
): string {
  const raw = String(message || "").trim();
  const key = API_ERROR_KEYS[raw];
  if (!key) return raw;
  const localized = t(key);
  return localized === key ? raw : localized;
}
