import type { Metadata } from "next";
import { Suspense } from "react";
import { BattleHistoryClient } from "@/components/play/BattleHistoryClient";
import { playPageMetadata } from "@/lib/playSeo";

export const metadata: Metadata = playPageMetadata({
  title: "對戰記錄 | OPCG 卡牌助手",
  description: "查看並回放已完成的 OPCG 對戰。",
  path: "/play/history",
});

export default function BattleHistoryPage() {
  return (
    <Suspense fallback={<p className="muted">…</p>}>
      <BattleHistoryClient />
    </Suspense>
  );
}
