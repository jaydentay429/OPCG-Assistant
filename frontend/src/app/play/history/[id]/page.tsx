import type { Metadata } from "next";
import { Suspense } from "react";
import { BattleReplayClient } from "@/components/play/BattleReplayClient";

type Props = {
  params: Promise<{ id: string }>;
};

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  return {
    title: { absolute: `對戰回放 · ${id.slice(0, 8)} | OPCG 卡牌助手` },
    robots: { index: false, follow: false },
  };
}

export default async function BattleReplayPage({ params }: Props) {
  const { id } = await params;
  return (
    <Suspense fallback={<p className="muted">…</p>}>
      <BattleReplayClient replayId={id} />
    </Suspense>
  );
}
