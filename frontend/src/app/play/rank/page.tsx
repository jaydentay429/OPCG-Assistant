import type { Metadata } from "next";
import { Suspense } from "react";
import { BattleRankClient } from "@/components/play/BattleRankClient";
import { playPageMetadata } from "@/lib/playSeo";

export const metadata: Metadata = playPageMetadata({
  title: "排位賽 | OPCG 卡牌助手",
  description: "OPCG 即時對戰排位：分數、段位與七武海／四皇／海賊王精英席排行榜。",
  path: "/play/rank",
});

export default function PlayRankPage() {
  return (
    <Suspense fallback={<p className="muted">…</p>}>
      <BattleRankClient />
    </Suspense>
  );
}
