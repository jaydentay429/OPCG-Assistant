import type { Metadata } from "next";
import { BinderSharedClient } from "@/components/BinderSharedClient";
import { buildPageMetadata } from "@/lib/seo";

export const metadata: Metadata = buildPageMetadata({
  title: "分享卡冊 | OPCG 卡牌助手",
  description: "查看分享的 OPCG 虛擬卡冊。",
  path: "/binder/s",
  absoluteTitle: true,
  noIndex: true,
});

export default async function BinderSharedPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  return <BinderSharedClient token={decodeURIComponent(token || "")} />;
}
