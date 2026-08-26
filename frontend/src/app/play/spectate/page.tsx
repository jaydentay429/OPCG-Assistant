import type { Metadata } from "next";
import { BattleSpectateClient } from "@/components/play/BattleSpectateClient";
import { buildPageMetadata } from "@/lib/seo";

export const metadata: Metadata = buildPageMetadata({
  title: "觀戰 | OPCG 卡牌助手",
  description: "觀看進行中的 OPCG 即時對戰。",
  path: "/play/spectate",
  absoluteTitle: true,
  noIndex: true,
});

export default function SpectatePage() {
  return <BattleSpectateClient />;
}
