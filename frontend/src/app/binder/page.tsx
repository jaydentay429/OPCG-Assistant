import type { Metadata } from "next";
import { BinderPageClient } from "@/components/BinderPageClient";
import { buildPageMetadata } from "@/lib/seo";

export const metadata: Metadata = buildPageMetadata({
  title: "卡冊排版 | OPCG 卡牌助手 - 規劃你的實體 Binder",
  description:
    "虛擬卡冊工具：把收藏卡牌排進頁面格子、調整版面與分享連結，方便規劃實體 binder 或展示你的 OPCG 收藏。",
  path: "/binder",
  absoluteTitle: true,
});

export default function BinderPage() {
  return <BinderPageClient />;
}
