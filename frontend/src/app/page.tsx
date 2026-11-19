import type { Metadata } from "next";
import { CoverLanding } from "@/components/CoverLanding";
import { HomeIndex } from "@/components/HomeIndex";
import { allSets } from "@/lib/sets";
import { BRAND_KEYWORDS, buildPageMetadata } from "@/lib/seo";
import { formatMetaLabel, loadLatestTournamentMetaKeys } from "@/lib/tournamentMeta";

export const revalidate = 3600;

export async function generateMetadata(): Promise<Metadata> {
  const keys = await loadLatestTournamentMetaKeys();
  const sets = formatMetaLabel(keys) || "最新環境";
  const catalog = allSets().filter((s) => s.code !== "DON");
  const latestOp = [...catalog.filter((s) => s.code.startsWith("OP"))].pop();
  const latestEb = [...catalog.filter((s) => s.code.startsWith("EB"))].pop();
  const extra = [
    latestOp ? `${latestOp.code} 卡表` : "",
    latestEb ? `${latestEb.code} 卡表` : "",
    "OPCG 線上對戰",
  ].filter(Boolean);
  return buildPageMetadata({
    title: "OPCG 卡牌助手 (optcgassistant) | OPCG Assistant 卡牌搜索・構築・賽事卡組・對戰",
    description:
      `optcgassistant.com（OPCG Card Assistant / OPCG Assistant）是航海王 ONE PIECE CARD GAME 工具站：卡牌資料庫、卡組構築、${sets} 賽事卡組、系列卡表、收藏卡冊、市場價格，以及瀏覽器即時對戰。搜尋 optcgassistant 即可找到本站。`,
    path: "/",
    absoluteTitle: true,
    keywords: [...BRAND_KEYWORDS, ...extra],
  });
}

export default function HomePage() {
  return (
    <>
      <CoverLanding />
      <HomeIndex />
    </>
  );
}
