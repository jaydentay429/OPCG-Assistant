import type { Metadata } from "next";
import { SearchPageClient } from "@/components/SearchPageClient";
import { HomeSeoIntro } from "@/components/SeoIntro";
import { BRAND_KEYWORDS, buildPageMetadata, breadcrumbJsonLd, jsonLdScript } from "@/lib/seo";
import { serverCopy } from "@/lib/serverCopy";

export async function generateMetadata(): Promise<Metadata> {
  const { lang, L } = await serverCopy();
  return buildPageMetadata({
    title: L(
      "卡牌搜索 | OPCG Assistant (optcgassistant) 卡牌資料庫",
      "Card Search | OPCG Assistant (optcgassistant) ONE PIECE Card Game Database",
    ),
    description: L(
      "在 optcgassistant.com（OPCG Assistant）查詢 ONE PIECE CARD GAME 卡牌：依卡號、卡名、顏色、費用、系列、稀有度與效果關鍵字篩選，支援中英日卡名。",
      "Search every ONE PIECE CARD GAME card on optcgassistant.com: filter by card number, name, color, cost, set, rarity and effect keywords, with English, Chinese and Japanese names.",
    ),
    path: "/search",
    absoluteTitle: true,
    lang,
    keywords: [
      ...BRAND_KEYWORDS,
      L("OPCG 搜索", "OPCG card search"),
      L("航海王卡牌資料庫", "ONE PIECE card database"),
      L("ONE PIECE 卡牌查詢", "OPTCG card list"),
      L("卡牌篩選", "card filter"),
    ],
  });
}

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string | string[] }>;
}) {
  const sp = await searchParams;
  const { L } = await serverCopy();
  const raw = sp.q;
  const initialQ = Array.isArray(raw) ? raw[0] || "" : raw || "";
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: jsonLdScript(
            breadcrumbJsonLd([
              { name: L("首頁", "Home"), path: "/" },
              { name: L("卡牌搜索", "Card search"), path: "/search" },
            ]),
          ),
        }}
      />
      <div className="route-fill">
        <SearchPageClient intro={<HomeSeoIntro />} initialQ={initialQ} />
      </div>
    </>
  );
}
