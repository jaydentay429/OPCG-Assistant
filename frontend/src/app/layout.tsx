import type { Metadata } from "next";
import localFont from "next/font/local";
import { ChunkLoadRecovery } from "@/components/ChunkLoadRecovery";
import { Providers } from "@/components/Providers";
import { TopBar } from "@/components/TopBar";
import { BottomNav } from "@/components/BottomNav";
import { FooterNote } from "@/components/FooterNote";
import { JsonLd } from "@/components/JsonLd";
import { SITE_NAME, SITE_NAME_EN, SITE_URL, defaultOgImage, rootJsonLd } from "@/lib/seo";
import { htmlLangAttr, localizedPath, ogLocale, type UrlLang } from "@/lib/localeRouting";
import { getRequestLang } from "@/lib/requestLang";
import { GoogleAnalytics } from "@next/third-parties/google";
import "./globals.css";

const syne = localFont({
  src: [
    { path: "./fonts/Syne-700.woff2", weight: "700", style: "normal" },
    { path: "./fonts/Syne-800.woff2", weight: "800", style: "normal" },
  ],
  variable: "--font-cover",
  display: "swap",
});

const og = defaultOgImage();

const ROOT_COPY: Record<UrlLang, { name: string; description: string; og: string; twitter: string }> = {
  "zh-Hant": {
    name: SITE_NAME,
    description:
      "航海王卡牌（OPCG）一站式助手：卡牌搜索、卡組構築、收藏與卡冊、市場價格，以及瀏覽器即時對戰（房間 PvP / AI）。",
    og: "航海王 OPCG 工具站：搜索、構築、收藏、市場價格與即時對戰（房間 / AI）。",
    twitter: "航海王 OPCG：卡牌搜索、卡組構築、收藏管理與即時對戰。",
  },
  "zh-Hans": {
    name: "OPCG 卡牌助手",
    description:
      "航海王卡牌（OPCG）一站式助手：卡牌搜索、卡组构筑、收藏与卡册、市场价格，以及浏览器实时对战（房间 PvP / AI）。",
    og: "航海王 OPCG 工具站：搜索、构筑、收藏、市场价格与实时对战（房间 / AI）。",
    twitter: "航海王 OPCG：卡牌搜索、卡组构筑、收藏管理与实时对战。",
  },
  en: {
    name: SITE_NAME_EN,
    description:
      "All-in-one ONE PIECE Card Game (OPCG) assistant: card search, deck builder, collection and binder, market prices, and live browser battles (rooms / AI).",
    og: "ONE PIECE Card Game tools: search, deck building, collection, market prices and live battles.",
    twitter: "ONE PIECE Card Game: card search, deck builder, collection and live battles.",
  },
};

export async function generateMetadata(): Promise<Metadata> {
  const lang = await getRequestLang();
  const copy = ROOT_COPY[lang];
  return {
    ...baseMetadata,
    title: { default: copy.name, template: `%s | ${copy.name}` },
    description: copy.description,
    openGraph: {
      ...baseMetadata.openGraph,
      locale: ogLocale(lang),
      title: copy.name,
      description: copy.og,
      url: `${SITE_URL}${localizedPath("/", lang)}`,
    },
    twitter: { ...baseMetadata.twitter, title: copy.name, description: copy.twitter },
    alternates: { canonical: localizedPath("/", lang) },
  };
}

const baseMetadata: Metadata = {
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

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const lang = await getRequestLang();
  return (
    <html lang={htmlLangAttr(lang)} className={syne.variable}>
      <head>
        <link rel="preconnect" href="https://img.optcgassistant.com" />
        <link rel="dns-prefetch" href="https://api.optcgassistant.com" />
      </head>
      <body>
        <JsonLd data={rootJsonLd()} />
        <Providers initialLang={lang}>
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
