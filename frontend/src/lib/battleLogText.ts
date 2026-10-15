import { BATTLE_CARD_ID_ONE } from "./battleLogCards";
import { hasCjk, localizeCardName, localizeCardText, preferLangText, toSimplifiedText } from "./cardLocale";
import type { Lang } from "./i18n";
import type { DeckStatFields } from "./api";

const OP_SUMMARY_KEYS: Record<string, string> = {
  skip_untap: "play.log.op_skip_untap",
  "skip_untap:leader": "play.log.op_skip_untap_leader",
  "skip_untap:own_leader": "play.log.op_skip_untap_own_leader",
  "skip_untap:all": "play.log.op_skip_untap_all",
  "skip_untap:don": "play.log.op_skip_untap_don",
};

export function isRawInstanceId(raw: string): boolean {
  const s = String(raw || "").trim();
  if (!s) return false;
  if (BATTLE_CARD_ID_ONE.test(s)) return false;
  return /^(ch|stg|stage|char|don|fx)_/i.test(s) || /^[a-z]+_[0-9a-f]{4,}$/i.test(s);
}

/** Leader / card name / human fallback. Instance ids never pass through. */
export function humanizeBattleUnit(
  raw: string,
  names: Record<string, DeckStatFields>,
  lang: Lang,
  t: (key: string, vars?: Record<string, string | number>) => string,
): string {
  const s = String(raw || "").trim();
  if (s === "character") return t("play.log.card_unnamed");
  if (!s || s === "leader" || /^leader-\d+$/.test(s)) return t("play.zone_leader");
  if (s === "don") return "DON!!";
  if (BATTLE_CARD_ID_ONE.test(s)) {
    return localizeCardName(names[s]?.name, names[s]?.name_en, lang) || s;
  }
  if (isRawInstanceId(s) || s.includes("{")) return t("play.log.card_unnamed");
  return s;
}

function cjkHalf(text: string, lang: Lang): string {
  const parts = text.split(/\s*\/\s*/).map((p) => p.trim()).filter(Boolean);
  const cjk = parts.filter((p) => hasCjk(p));
  if (!cjk.length) return "";
  const joined = cjk.join(" / ");
  return lang === "zh-Hans" ? toSimplifiedText(joined) : joined;
}

/** Drop English-only prompts in Chinese locales. Map raw op names to copy. */
export function humanizeEffectSummary(
  summary: string | null | undefined,
  lang: Lang,
  t: (key: string, vars?: Record<string, string | number>) => string,
): string {
  const raw = String(summary || "").trim();
  if (!raw) return "";
  const opKey = OP_SUMMARY_KEYS[raw];
  if (opKey) return t(opKey);
  if (/^[a-z0-9_:+.-]+$/i.test(raw) && /[_:]/.test(raw)) return t("play.log.op_generic");
  if (lang === "en") return preferLangText(raw, "en") || (!hasCjk(raw) ? raw : "");
  const bilingual = cjkHalf(raw, lang);
  if (bilingual) return bilingual;
  const localized = localizeCardText(raw, lang);
  if (!localized || !hasCjk(localized)) return "";
  return localized;
}

export function effectLogKey(key: string, hasCardId: boolean, summary: string): string {
  if (key !== "play.log.effect_applied" && key !== "play.log.effect_pending") return key;
  if (hasCardId && summary) return key;
  if (hasCardId) return `${key}_bare`;
  if (summary) return `${key}_summary`;
  return `${key}_bare`;
}
