import type { Metadata } from "next";
import { Suspense } from "react";
import { BattleReplayClient } from "@/components/play/BattleReplayClient";
import { playPageMetadata } from "@/lib/playSeo";

type Props = {
  params: Promise<{ id: string }>;
};

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  return playPageMetadata({
    title: `對戰回放 · ${id.slice(0, 8)} | OPCG 卡牌助手`,
    description: "查看已完成的 OPCG 對戰回放。",
    path: `/play/history/${encodeURIComponent(id)}`,
  });
}

export default async function BattleReplayPage({ params }: Props) {
  const { id } = await params;
  return (
    <Suspense fallback={<p className="muted">…</p>}>
      <BattleReplayClient replayId={id} />
    </Suspense>
  );
}
