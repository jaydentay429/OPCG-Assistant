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
  return <PricesPageClient />;
}
