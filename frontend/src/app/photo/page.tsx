import type { Metadata } from "next";
import { PhotoPageClient } from "@/components/PhotoPageClient";
import { PhotoSeoIntro } from "@/components/SeoIntro";
import { buildPageMetadata } from "@/lib/seo";

export const metadata: Metadata = buildPageMetadata({
  title: "拍照識卡 | OPCG 卡牌助手 - 手機拍照辨識卡號",
  description:
    "拍攝或上傳 OPCG 卡牌照片，自動辨識卡號與卡面，辨識後可直接查看卡牌效果、市場價格，或加入卡組與收藏，免去手動輸入卡號。",
  path: "/photo",
  absoluteTitle: true,
  keywords: ["OPCG 識卡", "卡牌掃描", "拍照查卡", "卡號辨識"],
});

export default function PhotoPage() {
  return (
    <>
      <PhotoSeoIntro />
      <PhotoPageClient />
    </>
  );
}
