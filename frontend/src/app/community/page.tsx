import type { Metadata } from "next";
import { Suspense } from "react";
import { CommunityHome } from "@/components/community/CommunityClient";
import { buildPageMetadata } from "@/lib/seo";

export const metadata: Metadata = buildPageMetadata({
  title: "社區 | OPCG 卡牌助手",
  description: "OPCG 社區論壇：組卡討論、卡牌交易與閒聊，與玩家交流航海王卡牌情報。",
  path: "/community",
  absoluteTitle: true,
  keywords: ["OPCG 社區", "卡牌論壇", "組卡討論"],
});

export default function CommunityPage() {
  return (
    <Suspense fallback={<p className="muted">…</p>}>
      <CommunityHome />
    </Suspense>
  );
}
