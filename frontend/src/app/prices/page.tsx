import type { Metadata } from "next";
import { PricesPageClient } from "@/components/PricesPageClient";
import { buildPageMetadata } from "@/lib/seo";

export const metadata: Metadata = buildPageMetadata({
  title: "卡牌市場價格查詢 | OPCG 卡牌助手",
  description:
    "查詢 OPCG 卡牌市場價格與行情參考，建立關注清單追蹤價格變化，協助補牌與買賣前快速比價。",
  path: "/prices",
  absoluteTitle: true,
  keywords: ["OPCG 價格", "卡牌行情", "yuyu-tei", "市場價格"],
});

export default function PricesPage() {
  return (
    <>
      <section className="page-seo-intro seo-only" aria-hidden="true">
        <p>
          本頁提供 ONE PIECE CARD GAME（OPCG）卡牌的市場行情參考，可搜尋卡號或卡名、加入關注清單，並對照日圓參考價。數字會隨市況更新，請以頁面上即時列表為準。
        </p>
        <p>
          價格來源為 Yuyu-tei 等公開店舖參考價，僅供補牌與比價，不是即時成交價或官方定價。
        </p>
      </section>
      <PricesPageClient />
    </>
  );
}
