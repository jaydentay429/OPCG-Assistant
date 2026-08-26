import type { Metadata } from "next";
import { CollectorPageClient } from "@/components/CollectorPageClient";
import { buildPageMetadata } from "@/lib/seo";

export const metadata: Metadata = buildPageMetadata({
  title: "收藏管理 | OPCG 卡牌助手 - 追蹤你的卡牌持有進度",
  description:
    "管理你的 OPCG 卡牌收藏：標記持有與數量、按系列或稀有度檢視進度，快速找出尚缺的卡牌並同步收藏狀態。",
  path: "/collector",
  absoluteTitle: true,
});

export default function CollectorPage() {
  return <CollectorPageClient />;
}
