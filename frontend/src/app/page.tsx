import type { Metadata } from "next";
import { CoverLanding } from "@/components/CoverLanding";
import { BRAND_KEYWORDS, buildPageMetadata } from "@/lib/seo";

export const metadata: Metadata = buildPageMetadata({
  title: "OPCG 卡牌助手 (optcgassistant) | OPCG Assistant 卡牌搜索・構築・賽事卡組・對戰",
  description:
    "optcgassistant.com（OPCG Card Assistant / OPCG Assistant）是航海王 ONE PIECE CARD GAME 工具站：卡牌資料庫、卡組構築、OP17/OP16 賽事卡組 deck list、收藏卡冊、市場價格，以及瀏覽器即時對戰。搜尋 optcgassistant、opcg assistant 即可找到本站。",
  path: "/",
  absoluteTitle: true,
  keywords: [...BRAND_KEYWORDS],
});

export default function HomePage() {
  return <CoverLanding />;
}
