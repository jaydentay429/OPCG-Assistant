/** Public origin. Never built from the incoming request host. */
export const PLAY_PAUSED_ORIGIN = "https://optcgassistant.com";

export function playPausedPath(slug?: string[]): string {
  const parts = (slug ?? []).map((part) => String(part || "").trim()).filter(Boolean);
  if (!parts.length) return "/play";
  return `/play/${parts.map((part) => encodeURIComponent(part)).join("/")}`;
}

export function playPausedMetadata(slug?: string[]) {
  const path = playPausedPath(slug);
  const canonical = `${PLAY_PAUSED_ORIGIN}${path}`;
  const description = "對戰功能暫停開放。搜卡、組牌、賽事卡組、收藏與價格仍可照常使用。";
  return {
    title: { absolute: "對戰功能暫停開放 | OPCG 卡牌助手" },
    description,
    robots: {
      index: false,
      follow: true,
      googleBot: { index: false, follow: true },
    },
    alternates: { canonical },
    openGraph: {
      title: "對戰功能暫停開放",
      description,
      url: canonical,
      siteName: "OPCG 卡牌助手",
    },
  };
}
