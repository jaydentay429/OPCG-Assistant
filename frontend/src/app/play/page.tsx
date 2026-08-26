import type { Metadata } from "next";
import { Suspense } from "react";
import { PlayPageClient } from "@/components/play/PlayPageClient";
import { PlaySeoIntro } from "@/components/SeoIntro";
import { SITE_URL, buildPageMetadata, jsonLdScript } from "@/lib/seo";

export const metadata: Metadata = buildPageMetadata({
  title: "即時對戰（房間 / AI）| OPCG 卡牌助手",
  description:
    "在瀏覽器進行 OPCG / 航海王卡牌即時對戰：建立房間與好友對戰，或挑戰 AI。載入自製卡組，練習回合、阻擋、反擊與卡牌效果，方便賽前練牌與熟悉規則。",
  path: "/play",
  absoluteTitle: true,
  keywords: [
    "OPCG 即時對戰",
    "航海王卡牌對戰",
    "ONE PIECE 卡牌線上對戰",
    "OPCG AI 對戰",
    "OPCG 房間對戰",
    "練牌",
  ],
});

const playJsonLd = {
  "@context": "https://schema.org",
  "@type": "WebApplication",
  name: "OPCG 即時對戰",
  url: `${SITE_URL}/play`,
  applicationCategory: "GameApplication",
  operatingSystem: "Web",
  description:
    "ONE PIECE CARD GAME 瀏覽器即時對戰：房間對戰與 AI 對戰，支援自製卡組載入。",
  isPartOf: {
    "@type": "WebSite",
    name: "OPCG 卡牌助手",
    url: SITE_URL,
  },
};

export default function PlayPage() {
  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLdScript(playJsonLd) }} />
      <PlaySeoIntro />
      <Suspense fallback={<p className="muted">…</p>}>
        <PlayPageClient />
      </Suspense>
    </>
  );
}
