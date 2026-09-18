import type { Metadata } from "next";
import { Suspense } from "react";
import { BuilderPageClient } from "@/components/BuilderPageClient";
import { buildPageMetadata } from "@/lib/seo";

// useSearchParams() inside BuilderPageClient forces the Suspense fallback into
// the static HTML shell otherwise — force per-request rendering so crawlers see
// the real <h1>/content instead of the "…" fallback.
export const dynamic = "force-dynamic";

export const metadata: Metadata = buildPageMetadata({
  title: "卡組構築 | OPCG 卡牌助手 - 打造你的最強牌組",
  description:
    "線上構築 OPCG / 航海王卡牌卡組：選擇領導卡、編輯主牌與費用曲線、檢查張數限制，並儲存或分享你的牌組列表。",
  path: "/builder",
  absoluteTitle: true,
  keywords: ["OPCG 卡組", "卡組構築", "deck builder", "航海王組牌"],
});

export default function BuilderPage() {
  return (
    <Suspense fallback={<p className="muted">…</p>}>
      <BuilderPageClient />
    </Suspense>
  );
}
