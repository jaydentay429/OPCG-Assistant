import type { Metadata } from "next";
import { Syne } from "next/font/google";
import { ChunkLoadRecovery } from "@/components/ChunkLoadRecovery";
import { Providers } from "@/components/Providers";
import { TopBar } from "@/components/TopBar";
import { BottomNav } from "@/components/BottomNav";
import { FooterNote } from "@/components/FooterNote";
import { JsonLd } from "@/components/JsonLd";
import { SITE_NAME, SITE_URL, defaultOgImage, rootJsonLd } from "@/lib/seo";
import { GoogleAnalytics } from "@next/third-parties/google";
import "./globals.css";

const syne = Syne({
  subsets: ["latin"],
  weight: ["700", "800"],
  variable: "--font-cover",
  display: "swap",
});

const og = defaultOgImage();

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: SITE_NAME,
    template: `%s | ${SITE_NAME}`,
  },
  description:
    "航海王卡牌（OPCG）一站式助手：卡牌搜索、卡組構築、收藏與卡冊、市場價格，以及瀏覽器即時對戰（房間 PvP / AI）。",
  applicationName: SITE_NAME,
  keywords: [
    "OPCG",
    "OPTCG",
    "ONE PIECE CARD GAME",
    "ONE PIECE 卡牌",
    "航海王卡牌",
    "OPCG 卡牌助手",
    "OPCG Card Assistant",
    "OPCG Assistant",
    "optcgassistant",
    "opcg assistant",
    "optcg assistant",
    "optcgassistant.com",
    "OP17 deck list",
    "OP16 deck list",
    "即時對戰",
    "線上對戰",
    "OPCG 對戰",
    "卡組構築",
    "卡牌搜索",
    "收藏管理",
    "卡冊",
    "市場價格",
    "賽事卡組",
    "AI 對戰",
  ],
  openGraph: {
    siteName: SITE_NAME,
    locale: "zh_HK",
    type: "website",
    title: SITE_NAME,
    description:
      "航海王 OPCG 工具站：搜索、構築、收藏、市場價格與即時對戰（房間 / AI）。",
    url: SITE_URL,
    images: [og],
  },
  twitter: {
    card: "summary_large_image",
    title: SITE_NAME,
    description: "航海王 OPCG：卡牌搜索、卡組構築、收藏管理與即時對戰。",
    images: [og.url],
  },
  alternates: {
    canonical: "/",
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-image-preview": "large",
      "max-snippet": -1,
      "max-video-preview": -1,
    },
  },
  icons: {
    icon: [{ url: "/favicon.ico" }],
  },
  category: "games",
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover" as const,
  themeColor: "#0b1220",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-HK" className={syne.variable}>
      <head>
        <link rel="preconnect" href="https://img.optcgassistant.com" />
        <link rel="dns-prefetch" href="https://api.optcgassistant.com" />
      </head>
      <body>
        <JsonLd data={rootJsonLd()} />
        <Providers>
          <ChunkLoadRecovery />
          <div className="app-shell">
            <TopBar />
            <main className="main">{children}</main>
            <FooterNote />
            <BottomNav />
          </div>
        </Providers>
        <GoogleAnalytics gaId="G-RWWB3EW28N" />
      </body>
    </html>
  );
}
