import type { Metadata } from "next";
import { SearchPageClient } from "@/components/SearchPageClient";
import { HomeSeoIntro } from "@/components/SeoIntro";
import { BRAND_KEYWORDS, buildPageMetadata, breadcrumbJsonLd, jsonLdScript } from "@/lib/seo";

export const metadata: Metadata = buildPageMetadata({
  title: "卡牌搜索 | OPCG Assistant (optcgassistant) 卡牌資料庫",
  description:
    "在 optcgassistant.com（OPCG Assistant）查詢 ONE PIECE CARD GAME 卡牌：依卡號、卡名、顏色、費用、系列、稀有度與效果關鍵字篩選，支援中英日卡名。",
  path: "/search",
  absoluteTitle: true,
  keywords: [...BRAND_KEYWORDS, "OPCG 搜索", "航海王卡牌資料庫", "ONE PIECE 卡牌查詢", "卡牌篩選"],
});

export default function SearchPage() {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: jsonLdScript(
            breadcrumbJsonLd([
              { name: "首頁", path: "/" },
              { name: "卡牌搜索", path: "/search" },
            ]),
          ),
        }}
      />
      <SearchPageClient intro={<HomeSeoIntro />} />
    </>
  );
}
