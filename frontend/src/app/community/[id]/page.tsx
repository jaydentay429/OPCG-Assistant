import type { Metadata } from "next";
import { Suspense } from "react";
import { CommunityThreadDetail } from "@/components/community/CommunityClient";
import { JsonLd } from "@/components/JsonLd";
import { fetchCommunityThread } from "@/lib/api";
import { buildPageMetadata, discussionForumPostingJsonLd } from "@/lib/seo";
import type { CommunityPost, CommunityThread } from "@/lib/types";

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

function publicAuthorName(thread: CommunityThread): string | undefined {
  if (thread.anonymous) return undefined;
  const name = String(thread.author_display || thread.username || "").trim();
  return name || undefined;
}

export default async function CommunityThreadPage({ params }: Props) {
  const { id } = await params;
  const threadId = Number(id);
  let thread: CommunityThread | null = null;
  let posts: CommunityPost[] = [];
  if (Number.isFinite(threadId) && threadId > 0) {
    try {
      const data = await fetchCommunityThread(threadId);
      thread = data.thread;
      posts = data.posts || [];
    } catch {
      thread = null;
    }
  }

  const showPosting = Boolean(thread && !thread.deleted);
  const posting =
    showPosting && thread
      ? discussionForumPostingJsonLd({
          id: thread.id,
          title: thread.title,
          body: thread.body || thread.excerpt,
          datePublished: thread.created_at,
          dateModified: thread.edited_at || thread.updated_at,
          authorName: publicAuthorName(thread),
        })
      : null;

  return (
    <>
      <JsonLd data={posting} />
      <Suspense fallback={<p className="muted">…</p>}>
        <CommunityThreadDetail threadId={threadId} initialThread={thread} initialPosts={posts} />
      </Suspense>
    </>
  );
}
