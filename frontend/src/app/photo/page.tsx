import type { Metadata } from "next";
import { PhotoPageClient } from "@/components/PhotoPageClient";
import { buildPageMetadata } from "@/lib/seo";

export const metadata: Metadata = buildPageMetadata({
  title: "拍照識卡 | OPCG 卡牌助手",
  description: "拍攝或上傳 OPCG 卡牌照片，快速辨識卡號與卡面，方便整理收藏與查價。",
  path: "/photo",
  absoluteTitle: true,
  keywords: ["OPCG 識卡", "卡牌掃描", "拍照查卡"],
});

export default function PhotoPage() {
  return <PhotoPageClient />;
}
