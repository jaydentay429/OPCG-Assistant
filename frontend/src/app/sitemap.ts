import fs from "fs";
import path from "path";
import type { MetadataRoute } from "next";
import bundledCardIds from "@/generated/card-ids.json";
import { toBaseCardId } from "@/lib/cardId";
import { sitemapCardIds } from "@/lib/parallelArts";
import { SITE_URL, cardOgImage } from "@/lib/seo";
import { allSets } from "@/lib/sets";

function loadCardIds(): string[] {
  if (Array.isArray(bundledCardIds) && bundledCardIds.length) {
    return bundledCardIds.filter(Boolean);
  }
  const candidates = [
    path.join(process.cwd(), "..", "index", "cards_by_id.json"),
    path.join(process.cwd(), "index", "cards_by_id.json"),
    path.join(process.cwd(), "..", "..", "index", "cards_by_id.json"),
  ];
  for (const file of candidates) {
    try {
      if (!fs.existsSync(file)) continue;
      const raw = JSON.parse(fs.readFileSync(file, "utf8")) as Record<string, unknown>;
      return Object.keys(raw).filter(Boolean).sort();
    } catch {
      // try next candidate
    }
  }
  return [];
}

export default function sitemap(): MetadataRoute.Sitemap {
  const lastModified = new Date();
  const staticRoutes: Array<{
    path: string;
    priority: number;
    changeFrequency: NonNullable<MetadataRoute.Sitemap[number]["changeFrequency"]>;
  }> = [
    { path: "/", priority: 1, changeFrequency: "daily" },
    { path: "/search", priority: 0.98, changeFrequency: "daily" },
    { path: "/play", priority: 0.95, changeFrequency: "daily" },
    { path: "/play/rank", priority: 0.7, changeFrequency: "daily" },
    { path: "/builder", priority: 0.9, changeFrequency: "weekly" },
    { path: "/tournaments", priority: 0.9, changeFrequency: "daily" },
    { path: "/collector", priority: 0.8, changeFrequency: "weekly" },
    { path: "/binder", priority: 0.8, changeFrequency: "weekly" },
    { path: "/prices", priority: 0.9, changeFrequency: "daily" },
    { path: "/community", priority: 0.85, changeFrequency: "daily" },
    { path: "/photo", priority: 0.6, changeFrequency: "monthly" },
    { path: "/sets", priority: 0.92, changeFrequency: "weekly" },
    { path: "/legal/privacy", priority: 0.2, changeFrequency: "yearly" },
    { path: "/legal/terms", priority: 0.2, changeFrequency: "yearly" },
    { path: "/legal/disclaimer", priority: 0.2, changeFrequency: "yearly" },
  ];

  const entries: MetadataRoute.Sitemap = staticRoutes.map(({ path: route, priority, changeFrequency }) => ({
    url: new URL(route, `${SITE_URL}/`).toString(),
    lastModified,
    changeFrequency,
    priority,
  }));

  for (const set of allSets()) {
    entries.push({
      url: new URL(`/sets/${encodeURIComponent(set.code)}`, `${SITE_URL}/`).toString(),
      lastModified,
      changeFrequency: "weekly",
      priority: 0.85,
    });
  }

  for (const cardId of sitemapCardIds(loadCardIds())) {
    const img = cardOgImage(cardId);
    const base = toBaseCardId(cardId);
    const isParallel = base !== cardId;
    entries.push({
      url: new URL(`/cards/${encodeURIComponent(cardId)}`, `${SITE_URL}/`).toString(),
      lastModified,
      changeFrequency: "weekly",
      priority: isParallel ? 0.55 : 0.72,
      ...(img ? { images: [img.url] } : {}),
    });
  }

  return entries;
}
