import type { Metadata } from "next";

export const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL || "https://optcgassistant.com").replace(
  /\/$/,
  "",
);
export const SITE_NAME = "OPCG 卡牌助手";
export const SITE_NAME_EN = "OPCG Card Assistant";

/** Brand aliases people actually type into Google / AI search. */
export const SITE_BRAND_ALIASES = [
  SITE_NAME_EN,
  "OPCG Assistant",
  "optcg assistant",
  "opcg assistant",
  "optcgassistant",
  "opcgassistant",
  "optcgassistant.com",
  "OPCG卡牌助手",
  "航海王卡牌助手",
] as const;

export const BRAND_KEYWORDS = [
  "OPCG",
  "OPTCG",
  "ONE PIECE CARD GAME",
  "ONE PIECE 卡牌",
  "航海王卡牌",
  "OPCG 卡牌助手",
  "OPCG Card Assistant",
  "OPCG Assistant",
  "optcgassistant",
  "opcg assistant",
  "optcg assistant",
  "optcgassistant.com",
  "OPCG deck builder",
  "OPCG deck list",
  "OP17 deck list",
  "OP16 deck list",
  "ONE PIECE TCG deck list",
  "卡組構築",
  "卡牌搜索",
  "賽事卡組",
  "即時對戰",
] as const;

const PACKS_CDN =
  (process.env.NEXT_PUBLIC_PACKS_CDN_URL || "").replace(/\/$/, "") ||
  (SITE_URL.includes("optcgassistant.com") ? "https://img.optcgassistant.com" : "");

/** Absolute URL helper. */
export function absoluteUrl(path = "/"): string {
  if (/^https?:\/\//i.test(path)) return path;
  return new URL(path.startsWith("/") ? path : `/${path}`, `${SITE_URL}/`).toString();
}

/** Default social share image (App Router opengraph-image). */
export function defaultOgImage(): { url: string; width: number; height: number; alt: string } {
  return {
    url: absoluteUrl("/opengraph-image"),
    width: 1200,
    height: 630,
    alt: SITE_NAME,
  };
}

/** Card art for Open Graph / Twitter. Prefer CDN for crawlability. */
export function cardOgImage(
  cardId: string,
): { url: string; width: number; height: number; alt: string } | null {
  const id = String(cardId || "").trim();
  if (!id) return null;
  const url = PACKS_CDN
    ? `${PACKS_CDN}/${encodeURIComponent(id)}.png`
    : `https://api.optcgassistant.com/packs/${encodeURIComponent(id)}.png`;
  return {
    url,
    width: 733,
    height: 1024,
    alt: id,
  };
}

type PageMetaInput = {
  title: string;
  description: string;
  path: string;
  keywords?: string[];
  type?: "website" | "article";
  images?: Array<{ url: string; width?: number; height?: number; alt?: string }>;
  noIndex?: boolean;
  absoluteTitle?: boolean;
};

/** Shared page metadata with OG + Twitter + canonical. */
export function buildPageMetadata(input: PageMetaInput): Metadata {
  const images = input.images?.length ? input.images : [defaultOgImage()];
  const canonical = input.path.startsWith("http") ? input.path : input.path;
  return {
    title: input.absoluteTitle ? { absolute: input.title } : input.title,
    description: input.description,
    keywords: input.keywords,
    alternates: {
      canonical,
      languages: {
        "zh-HK": canonical,
        "zh-CN": canonical,
        en: canonical,
        "x-default": canonical,
      },
    },
    openGraph: {
      title: input.title,
      description: input.description,
      url: canonical,
      siteName: SITE_NAME,
      locale: "zh_HK",
      type: input.type || "website",
      images,
    },
    twitter: {
      card: "summary_large_image",
      title: input.title,
      description: input.description,
      images: images.map((img) => img.url),
    },
    robots: input.noIndex
      ? { index: false, follow: false, googleBot: { index: false, follow: false } }
      : { index: true, follow: true },
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function isFaqPage(value: unknown): boolean {
  if (!isRecord(value)) return false;
  const type = value["@type"];
  return type === "FAQPage" || (Array.isArray(type) && type.includes("FAQPage"));
}

/**
 * FAQPage is valid only when the same questions and answers are visible on that page.
 * Shared layout data and the card-page schema do not have a visible FAQ, so drop it.
 * Pass `{ allowFaq: true }` only from a page that renders the matching Q&A in the UI.
 */
function omitFaqPageJsonLd(value: unknown): unknown {
  if (isFaqPage(value)) return undefined;
  if (Array.isArray(value)) {
    return value.filter((item) => !isFaqPage(item)).map((item) => omitFaqPageJsonLd(item));
  }
  if (!isRecord(value)) return value;
  const next: Record<string, unknown> = {};
  for (const [key, child] of Object.entries(value)) {
    if (isFaqPage(child)) continue;
    const cleaned = omitFaqPageJsonLd(child);
    if (cleaned !== undefined) next[key] = cleaned;
  }
  return next;
}

export function jsonLdScript(
  data: Record<string, unknown> | Array<Record<string, unknown>>,
  options?: { allowFaq?: boolean },
): string {
  const payload = options?.allowFaq ? data : omitFaqPageJsonLd(data);
  return JSON.stringify(payload ?? null).replace(/</g, "\\u003c");
}

/** Root structured data: WebSite + SearchAction + Organization + WebApplication. */
export function rootJsonLd(): Record<string, unknown> {
  const aliases = [...SITE_BRAND_ALIASES];
  return {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Organization",
        "@id": `${SITE_URL}/#organization`,
        name: SITE_NAME,
        legalName: SITE_NAME_EN,
        alternateName: aliases,
        url: SITE_URL,
        logo: absoluteUrl("/opengraph-image"),
        description:
          "Unofficial ONE PIECE CARD GAME (OPCG / OPTCG) fan toolkit: card database, deck builder, tournament deck lists, collection tools, and browser practice battles. Also known as OPCG Assistant / optcgassistant.",
      },
      {
        "@type": "WebSite",
        "@id": `${SITE_URL}/#website`,
        url: SITE_URL,
        name: `${SITE_NAME} (optcgassistant.com)`,
        alternateName: aliases,
        inLanguage: ["zh-HK", "zh-CN", "en"],
        publisher: { "@id": `${SITE_URL}/#organization` },
        potentialAction: {
          "@type": "SearchAction",
          target: {
            "@type": "EntryPoint",
            urlTemplate: `${SITE_URL}/search?q={search_term_string}`,
          },
          "query-input": "required name=search_term_string",
        },
      },
      {
        "@type": "WebApplication",
        "@id": `${SITE_URL}/#app`,
        name: SITE_NAME,
        alternateName: aliases,
        url: SITE_URL,
        applicationCategory: "GameApplication",
        operatingSystem: "Web",
        inLanguage: ["zh-HK", "zh-CN", "en"],
        isPartOf: { "@id": `${SITE_URL}/#website` },
        description:
          "ONE PIECE CARD GAME（OPCG）工具網站 optcgassistant.com：卡牌資料庫、卡組構築、賽事卡組（OP17 / OP16 deck list）、收藏與卡冊、市場價格，以及瀏覽器即時對戰（房間對戰與 AI 對戰）。",
        featureList: [
          "卡牌搜索與篩選",
          "卡組構築 / deck builder",
          "賽事卡組 / tournament deck lists",
          "收藏管理",
          "卡冊排版",
          "市場價格",
          "即時對戰（房間 PvP）",
          "AI 對戰",
        ],
        offers: {
          "@type": "Offer",
          price: "0",
          priceCurrency: "HKD",
        },
      },
      {
        "@type": "FAQPage",
        "@id": `${SITE_URL}/#faq`,
        mainEntity: [
          {
            "@type": "Question",
            name: "OPCG 卡牌助手是官方網站嗎？",
            acceptedAnswer: {
              "@type": "Answer",
              text: "不是。optcgassistant.com 是非官方粉絲工具，與 BANDAI / 東映動畫無關聯。卡名、效果與卡圖屬權利人所有。",
            },
          },
          {
            "@type": "Question",
            name: "怎麼查航海王卡牌效果與卡號？",
            acceptedAnswer: {
              "@type": "Answer",
              text: "打開卡牌搜索，輸入卡號（如 OP01-001）或中文／英文卡名即可篩選顏色、費用、系列與效果關鍵字。",
            },
          },
          {
            "@type": "Question",
            name: "可以在瀏覽器練牌或對戰嗎？",
            acceptedAnswer: {
              "@type": "Answer",
              text: "可以。即時對戰支援房間對戰與 AI 對戰，訪客可用範例卡組一鍵開始，無需先組好 50 張。",
            },
          },
          {
            "@type": "Question",
            name: "哪裡看 OP18、EB05 等系列全卡表？",
            acceptedAnswer: {
              "@type": "Answer",
              text: "系列卡表在 /sets，例如 /sets/OP18、/sets/EB05，可點進每張卡查看效果與價格。",
            },
          },
        ],
      },
    ],
  };
}

/** Product-like JSON-LD for a card detail page. */
export function cardJsonLd(input: {
  id: string;
  name: string;
  nameEn?: string;
  description: string;
  imageUrl?: string | null;
  rarity?: string;
  series?: string;
}): Record<string, unknown> {
  const url = absoluteUrl(`/cards/${encodeURIComponent(input.id)}`);
  return {
    "@context": "https://schema.org",
    "@type": "Product",
    name: input.nameEn && input.nameEn !== input.name ? `${input.name} / ${input.nameEn}` : input.name,
    sku: input.id,
    productID: input.id,
    description: input.description,
    url,
    image: input.imageUrl ? [input.imageUrl] : undefined,
    brand: {
      "@type": "Brand",
      name: "ONE PIECE CARD GAME",
    },
    category: "Trading Card Game",
    additionalProperty: [
      input.rarity
        ? { "@type": "PropertyValue", name: "Rarity", value: input.rarity }
        : null,
      input.series
        ? { "@type": "PropertyValue", name: "Set", value: input.series }
        : null,
    ].filter(Boolean),
    isPartOf: {
      "@type": "WebSite",
      name: SITE_NAME,
      url: SITE_URL,
    },
  };
}

export function breadcrumbJsonLd(
  items: Array<{ name: string; path: string }>,
): Record<string, unknown> {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((item, index) => ({
      "@type": "ListItem",
      position: index + 1,
      name: item.name,
      item: absoluteUrl(item.path),
    })),
  };
}

export function faqPageJsonLd(
  items: Array<{ question: string; answer: string }>,
): Record<string, unknown> | null {
  const mainEntity = items
    .map((item) => {
      const question = item.question.trim();
      const answer = item.answer.trim();
      if (!question || !answer) return null;
      return {
        "@type": "Question",
        name: question,
        acceptedAnswer: { "@type": "Answer", text: answer },
      };
    })
    .filter((row): row is NonNullable<typeof row> => row != null);
  if (!mainEntity.length) return null;
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity,
  };
}

/** Forum post JSON-LD. Only include fields we actually fetched. */
export function discussionForumPostingJsonLd(input: {
  id: number;
  title: string;
  body?: string;
  datePublished?: string;
  dateModified?: string;
  authorName?: string;
}): Record<string, unknown> | null {
  const title = String(input.title || "").trim();
  if (!title) return null;
  const text = String(input.body || "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 5000);
  const node: Record<string, unknown> = {
    "@context": "https://schema.org",
    "@type": "DiscussionForumPosting",
    headline: title,
    url: absoluteUrl(`/community/${input.id}`),
  };
  if (text) node.text = text;
  if (input.datePublished) node.datePublished = input.datePublished;
  if (input.dateModified) node.dateModified = input.dateModified;
  if (input.authorName) {
    node.author = { "@type": "Person", name: input.authorName };
  }
  return node;
}
