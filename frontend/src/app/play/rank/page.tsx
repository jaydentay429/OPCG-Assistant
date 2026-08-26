import type { Metadata } from "next";
import { Suspense } from "react";
import { BattleRankClient } from "@/components/play/BattleRankClient";
import { buildPageMetadata } from "@/lib/seo";

export const metadata: Metadata = buildPageMetadata({
  title: "排位賽 | OPCG 卡牌助手",
  description: "OPCG 即時對戰排位：分數、段位與七武海／四皇／海賊王精英席排行榜。",
  path: "/play/rank",
  absoluteTitle: true,
});

export default function PlayRankPage() {
  return (
    <Suspense fallback={<p className="muted">…</p>}>
      <BattleRankClient />
    </Suspense>
  );
}
