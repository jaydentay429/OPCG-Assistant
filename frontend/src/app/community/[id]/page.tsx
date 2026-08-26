import type { Metadata } from "next";
import { Suspense } from "react";
import { CommunityThreadDetail } from "@/components/community/CommunityClient";
import { fetchCommunityThread } from "@/lib/api";
import { buildPageMetadata } from "@/lib/seo";

type Props = { params: Promise<{ id: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  const threadId = Number(id);
  if (!Number.isFinite(threadId) || threadId <= 0) {
    return buildPageMetadata({
      title: "帖子 | OPCG 社區",
      description: "OPCG 社區討論帖。",
      path: `/community/${id}`,
      absoluteTitle: true,
    });
  }

  try {
    const { thread } = await fetchCommunityThread(threadId);
    if (thread.deleted) {
      return buildPageMetadata({
        title: "帖子已刪除 | OPCG 社區",
        description: "此帖子已不可用。",
        path: `/community/${threadId}`,
        absoluteTitle: true,
        noIndex: true,
      });
    }
    const excerpt = String(thread.excerpt || thread.body || "")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 140);
    return buildPageMetadata({
      title: `${thread.title} | OPCG 社區`,
      description: excerpt || `OPCG 社區討論：${thread.title}`,
      path: `/community/${threadId}`,
      absoluteTitle: true,
      type: "article",
    });
  } catch {
    return buildPageMetadata({
      title: "帖子 | OPCG 社區",
      description: "OPCG 社區討論帖。",
      path: `/community/${threadId}`,
      absoluteTitle: true,
    });
  }
}

export default async function CommunityThreadPage({ params }: Props) {
  const { id } = await params;
  const threadId = Number(id);
  return (
    <Suspense fallback={<p className="muted">…</p>}>
      <CommunityThreadDetail threadId={threadId} />
    </Suspense>
  );
}
