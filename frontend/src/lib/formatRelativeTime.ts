import type { Lang } from "./i18n";

type TFn = (key: string, params?: Record<string, string | number>) => string;

export function formatRelativeTime(iso: string, lang: Lang, t: TFn): string {
  let ms: number;
  try {
    ms = new Date(iso).getTime();
  } catch {
    return iso;
  }
  if (Number.isNaN(ms)) return iso;
  const diffSec = Math.max(0, Math.floor((Date.now() - ms) / 1000));
  if (diffSec < 60) return t("community.time_just_now");
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return t("community.time_minutes", { n: diffMin });
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return t("community.time_hours", { n: diffHr });
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 14) return t("community.time_days", { n: diffDay });
  try {
    return new Date(ms).toLocaleDateString(lang === "en" ? "en-US" : lang === "zh-Hans" ? "zh-CN" : "zh-HK");
  } catch {
    return iso;
  }
}
