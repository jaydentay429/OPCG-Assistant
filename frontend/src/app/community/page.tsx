import type { Metadata } from "next";
import { Suspense } from "react";
import { CommunityHome } from "@/components/community/CommunityClient";
import { CommunitySeoIntro } from "@/components/SeoIntro";
import { fetchCommunityThreads } from "@/lib/api";
import { buildPageMetadata } from "@/lib/seo";

export const metadata: Metadata = buildPageMetadata({
  title: "社區論壇 | OPCG 卡牌助手 - 組卡討論、賽制規則與卡牌交易",
  description:
    "OPCG 卡牌助手社區論壇：依分區瀏覽或發帖，涵蓋組卡討論、賽制規則、卡牌交易與閒聊，可用標籤與熱門／最新排序找討論串，發帖可選擇匿名。",
  path: "/community",
  absoluteTitle: true,
  keywords: ["OPCG 社區", "卡牌論壇", "組卡討論", "卡牌交易", "賽制規則"],
});

export default async function CommunityPage() {
  let initialThreads = undefined;
  let initialTotal = undefined;
  let initialHasMore = undefined;
  try {
    const res = await fetchCommunityThreads({ sort: "new", limit: 30, offset: 0 });
    initialThreads = res.threads;
    initialTotal = res.total;
    initialHasMore = res.has_more;
  } catch {
    /* list still loads on the client */
  }

  return (
    <>
      <CommunitySeoIntro />
      <Suspense fallback={<p className="muted">…</p>}>
        <CommunityHome
          initialThreads={initialThreads}
          initialTotal={initialTotal}
          initialHasMore={initialHasMore}
        />
      </Suspense>
    </>
  );
}
