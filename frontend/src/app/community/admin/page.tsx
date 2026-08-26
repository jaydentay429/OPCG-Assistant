import type { Metadata } from "next";
import { Suspense } from "react";
import { CommunityAdminClient } from "@/components/community/CommunityAdminClient";
import { buildPageMetadata } from "@/lib/seo";

export const metadata: Metadata = buildPageMetadata({
  title: "社區管理 | OPCG",
  description: "OPCG 社區管理後台。",
  path: "/community/admin",
  absoluteTitle: true,
  noIndex: true,
});

export default function CommunityAdminPage() {
  return (
    <Suspense fallback={<p className="muted">…</p>}>
      <CommunityAdminClient />
    </Suspense>
  );
}
