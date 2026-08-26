import type { Lang } from "@/lib/i18n";
import type { CommunityCategory, CommunityTag } from "@/lib/types";

export function catTitle(c: CommunityCategory | { category_title_zh_hant?: string; category_title_zh_hans?: string; category_title_en?: string; title_zh_hant?: string; title_zh_hans?: string; title_en?: string }, lang: Lang): string {
  if ("title_zh_hant" in c && c.title_zh_hant) {
    if (lang === "en") return c.title_en || c.title_zh_hant;
    if (lang === "zh-Hans") return c.title_zh_hans || c.title_zh_hant;
    return c.title_zh_hant;
  }
  if (lang === "en") return c.category_title_en || c.category_title_zh_hant || "";
  if (lang === "zh-Hans") return c.category_title_zh_hans || c.category_title_zh_hant || "";
  return c.category_title_zh_hant || "";
}

export function tagTitle(tg: CommunityTag, lang: Lang): string {
  if (lang === "en") return tg.title_en;
  if (lang === "zh-Hans") return tg.title_zh_hans;
  return tg.title_zh_hant;
}

export function displayName(
  author: {
    anonymous: boolean;
    author_display: string;
    username?: string | null;
    is_self?: boolean;
    is_author_admin?: boolean;
  },
  t: (key: string) => string,
): string {
  if (author.is_author_admin && !author.anonymous) {
    return t("community.staff_name");
  }
  if (author.anonymous && !author.is_self) return t("community.anonymous");
  if (author.anonymous && author.is_self) {
    return `${t("community.anonymous")} (${author.username || t("community.you")})`;
  }
  return author.username || author.author_display || t("community.anonymous");
}

export function categoryClass(slug?: string | null): string {
  const s = String(slug || "").trim();
  if (!s) return "";
  return `cat-${s.replace(/[^a-z0-9_-]/gi, "")}`;
}
