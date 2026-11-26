import type { Metadata } from "next";
import { CoverLanding } from "@/components/CoverLanding";
import { HomeIndex } from "@/components/HomeIndex";
import { allSets } from "@/lib/sets";
import { BRAND_KEYWORDS, buildPageMetadata } from "@/lib/seo";
import { serverCopy } from "@/lib/serverCopy";
import { formatMetaLabel, loadLatestTournamentMetaKeys } from "@/lib/tournamentMeta";

export async function generateMetadata(): Promise<Metadata> {
  const { lang, L } = await serverCopy();
  const keys = await loadLatestTournamentMetaKeys();
  const sets = formatMetaLabel(keys) || L("最新環境", "the latest format");
  const catalog = allSets().filter((s) => s.code !== "DON");
  const latestOp = [...catalog.filter((s) => s.code.startsWith("OP"))].pop();
  const latestEb = [...catalog.filter((s) => s.code.startsWith("EB"))].pop();
  const extra = [
    latestOp ? L(`${latestOp.code} 卡表`, `${latestOp.code} card list`) : "",
    latestEb ? L(`${latestEb.code} 卡表`, `${latestEb.code} card list`) : "",
    L("OPCG 線上對戰", "OPCG online battle"),
  ].filter(Boolean);
  return buildPageMetadata({
    title: L(
      "OPCG 卡牌助手 (optcgassistant) | OPCG Assistant 卡牌搜索・構築・賽事卡組・對戰",
      "OPCG Card Assistant (optcgassistant) | ONE PIECE Card Game database, deck builder, tournament decks & battles",
    ),
    description: L(
      `optcgassistant.com（OPCG Card Assistant / OPCG Assistant）是航海王 ONE PIECE CARD GAME 工具站：卡牌資料庫、卡組構築、${sets} 賽事卡組、系列卡表、收藏卡冊、市場價格，以及瀏覽器即時對戰。搜尋 optcgassistant 即可找到本站。`,
      `optcgassistant.com (OPCG Card Assistant) is a free ONE PIECE CARD GAME toolkit: card database, deck builder, ${sets} tournament deck lists, set lists, collection binder, Japanese market prices and live browser battles.`,
    ),
    path: "/",
    absoluteTitle: true,
    lang,
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
