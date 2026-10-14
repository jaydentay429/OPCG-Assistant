import type { Metadata } from "next";
import { BattleSpectateClient } from "@/components/play/BattleSpectateClient";
import { playPageMetadata } from "@/lib/playSeo";

export const metadata: Metadata = playPageMetadata({
  title: "觀戰 | OPCG 卡牌助手",
  description: "觀看進行中的 OPCG 即時對戰。",
  path: "/play/spectate",
});

export default function SpectatePage() {
  return <BattleSpectateClient />;
}