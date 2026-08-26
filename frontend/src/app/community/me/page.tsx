import type { Metadata } from "next";
import { CommunityMeClient } from "@/components/community/CommunityMeClient";
import { buildPageMetadata } from "@/lib/seo";

export const metadata: Metadata = buildPageMetadata({
  title: "我的帖子 | OPCG 社區",
  description: "管理你在 OPCG 社區的帖子與回覆。",
  path: "/community/me",
  absoluteTitle: true,
  noIndex: true,
});

export default function CommunityMePage() {
  return <CommunityMeClient />;
}
