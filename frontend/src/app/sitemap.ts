import fs from "fs";
import path from "path";
import type { MetadataRoute } from "next";
import bundledCardIds from "@/generated/card-ids.json";
import { normalizeCardId, toBaseCardId } from "@/lib/cardId";
import { sitemapCardIds } from "@/lib/parallelArts";
import { sitemapCardImageLoc } from "@/lib/resolveCardImage";
import { SITE_URL } from "@/lib/seo";
import { allSets } from "@/lib/sets";

const INDEX_CANDIDATES = [
  path.join(process.cwd(), "..", "index", "cards_by_id.json"),
  path.join(process.cwd(), "index", "cards_by_id.json"),
  path.join(process.cwd(), "..", "..", "index", "cards_by_id.json"),
];

function readCardIndex(): Record<string, unknown> | null {
  for (const file of INDEX_CANDIDATES) {
    try {
      if (!fs.existsSync(file)) continue;
      return JSON.parse(fs.readFileSync(file, "utf8")) as Record<string, unknown>;
    } catch {
      // try next candidate
    }
  }
  return null;
}

function loadCardIds(): string[] {
  if (Array.isArray(bundledCardIds) && bundledCardIds.length) {
    return bundledCardIds.filter(Boolean);
  }
  const raw = readCardIndex();
  return raw ? Object.keys(raw).filter(Boolean).sort() : [];
}

/** Catalog ids whose stored img_url is non-empty. Step ① needs that gate. */
function loadIdsWithImgUrl(): Set<string> {
  const raw = readCardIndex();
  const ids = new Set<string>();
  if (!raw) return ids;
  for (const [key, value] of Object.entries(raw)) {
    if (!value || typeof value !== "object") continue;
    const row = value as { img_url?: unknown; card_id?: unknown; id?: unknown };
    if (!String(row.img_url || "").trim()) continue;
    const id = normalizeCardId(String(row.card_id || row.id || key));
    if (id) ids.add(id);
  }
  return ids;
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

  const withImgUrl = loadIdsWithImgUrl();
  for (const cardId of sitemapCardIds(loadCardIds())) {
    const id = normalizeCardId(cardId);
    const base = toBaseCardId(id);
    const isParallel = base !== id;
    const image = sitemapCardImageLoc({
      id,
      img_url: withImgUrl.has(id) ? "present" : "",
    });
    entries.push({
      url: new URL(`/cards/${encodeURIComponent(cardId)}`, `${SITE_URL}/`).toString(),
      lastModified,
      changeFrequency: "weekly",
      priority: isParallel ? 0.55 : 0.72,
      ...(image ? { images: [image] } : {}),
    });
  }

  return entries;
}
