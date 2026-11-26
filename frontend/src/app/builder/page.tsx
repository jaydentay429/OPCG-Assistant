import type { Metadata } from "next";
import { Suspense } from "react";
import { BuilderPageClient } from "@/components/BuilderPageClient";
import { buildPageMetadata } from "@/lib/seo";
import { serverCopy } from "@/lib/serverCopy";

// useSearchParams() inside BuilderPageClient forces the Suspense fallback into
// the static HTML shell otherwise — force per-request rendering so crawlers see
// the real <h1>/content instead of the "…" fallback.
export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  const { lang, L } = await serverCopy();
  return buildPageMetadata({
    title: L(
      "卡組構築 | OPCG 卡牌助手 - 打造你的最強牌組",
      "Deck Builder | OPCG Card Assistant - build your ONE PIECE Card Game deck",
    ),
    description: L(
      "線上構築 OPCG / 航海王卡牌卡組：選擇領導卡、編輯主牌與費用曲線、檢查張數限制，並儲存或分享你的牌組列表。",
      "Build ONE PIECE Card Game (OPCG) decks online: pick a leader, edit the main deck and cost curve, check copy limits, then save or share your deck list.",
    ),
    path: "/builder",
    absoluteTitle: true,
    lang,
    keywords: [L("OPCG 卡組", "OPCG deck"), L("卡組構築", "OPTCG deck builder"), "deck builder", L("航海王組牌", "ONE PIECE TCG deck")],
  });
}

export default function BuilderPage() {
  return (
    <Suspense fallback={<p className="muted">…</p>}>
      <BuilderPageClient />
    </Suspense>
  );
}
