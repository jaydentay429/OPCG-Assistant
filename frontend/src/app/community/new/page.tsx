import type { Metadata } from "next";
import { Suspense } from "react";
import { CommunityNewThread } from "@/components/community/CommunityClient";
import { buildPageMetadata } from "@/lib/seo";

export const metadata: Metadata = buildPageMetadata({
  title: "發帖 | OPCG 社區",
  description: "在 OPCG 社區發表新帖。",
  path: "/community/new",
  absoluteTitle: true,
  noIndex: true,
});

export default function CommunityNewPage() {
  return (
    <Suspense fallback={<p className="muted">…</p>}>
      <CommunityNewThread />
    </Suspense>
  );
}
