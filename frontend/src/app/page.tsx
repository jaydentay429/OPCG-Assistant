import type { Metadata } from "next";
import { CoverLanding } from "@/components/CoverLanding";
import { HomeIndex } from "@/components/HomeIndex";
import { BRAND_KEYWORDS, buildPageMetadata } from "@/lib/seo";

export const metadata: Metadata = buildPageMetadata({
  title: "OPCG 卡牌助手 (optcgassistant) | OPCG Assistant 卡牌搜索・構築・賽事卡組・對戰",
  description:
    "optcgassistant.com（OPCG Card Assistant / OPCG Assistant）是航海王 ONE PIECE CARD GAME 工具站：卡牌資料庫、卡組構築、OP18/OP17 賽事卡組、系列卡表、收藏卡冊、市場價格，以及瀏覽器即時對戰。搜尋 optcgassistant 即可找到本站。",
  path: "/",
  absoluteTitle: true,
  keywords: [...BRAND_KEYWORDS, "OP18 卡表", "EB05 卡表", "OPCG 線上對戰"],
});

export default function HomePage() {
  return (
    <>
      <CoverLanding />
      <HomeIndex />
    </>
  );
}
