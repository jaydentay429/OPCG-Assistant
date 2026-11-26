import type { Metadata } from "next";
import { PricesPageClient } from "@/components/PricesPageClient";
import { buildPageMetadata } from "@/lib/seo";
import { serverCopy } from "@/lib/serverCopy";

export async function generateMetadata(): Promise<Metadata> {
  const { lang, L } = await serverCopy();
  return buildPageMetadata({
    title: L("卡牌市場價格查詢 | OPCG 卡牌助手", "Card Market Prices | OPCG Card Assistant"),
    description: L(
      "查詢 OPCG 卡牌市場價格與行情參考，建立關注清單追蹤價格變化，協助補牌與買賣前快速比價。",
      "Check ONE PIECE Card Game (OPCG) market prices from Japan, keep a watchlist to follow price changes, and compare before you buy or sell.",
    ),
    path: "/prices",
    absoluteTitle: true,
    lang,
    keywords: [L("OPCG 價格", "OPCG prices"), L("卡牌行情", "OPTCG card prices"), "yuyu-tei", L("市場價格", "market price")],
  });
}

export default async function PricesPage() {
  const { L } = await serverCopy();
  return (
    <>
      <section className="page-seo-intro seo-only" aria-hidden="true">
        <p>
          {L(
            "本頁提供 ONE PIECE CARD GAME（OPCG）卡牌的市場行情參考，可搜尋卡號或卡名、加入關注清單，並對照日圓參考價。數字會隨市況更新，請以頁面上即時列表為準。",
            "Reference market prices for ONE PIECE CARD GAME (OPCG) cards: search by card number or name, add cards to a watchlist and compare yen reference prices. Numbers follow the market; the live list on this page is the current one.",
          )}
        </p>
        <p>
          {L(
            "價格來源為 Yuyu-tei 等公開店舖參考價，僅供補牌與比價，不是即時成交價或官方定價。",
            "Prices come from public shop listings such as Yuyu-tei. They are for reference only, not live sale prices or official pricing.",
          )}
        </p>
      </section>
      <PricesPageClient />
    </>
  );
}
