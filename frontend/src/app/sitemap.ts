import fs from "fs";
import path from "path";
import type { MetadataRoute } from "next";
import bundledCardIds from "@/generated/card-ids.json";
import cardLastmod from "@/generated/card-lastmod.json";
import { normalizeCardId, toBaseCardId } from "@/lib/cardId";
import { LEADER_INDEX_MIN_DECKS, fetchLeaders } from "@/lib/leaders";
import { localizedPath, type UrlLang } from "@/lib/localeRouting";
import { sitemapCardIds } from "@/lib/parallelArts";
import { manifestOwnImageCount, sitemapCardImageLoc } from "@/lib/resolveCardImage";
import { SITE_URL } from "@/lib/seo";
import { allSets } from "@/lib/sets";

// Leader rows come from the API; refresh hourly instead of freezing them at build.
export const revalidate = 3600;

const INDEX_CANDIDATES = [
  path.join(process.cwd(), "..", "index", "cards_by_id.json"),
  path.join(process.cwd(), "index", "cards_by_id.json"),
  path.join(process.cwd(), "..", "..", "index", "cards_by_id.json"),
];

const LANGS: UrlLang[] = ["zh-Hant", "zh-Hans", "en"];

/** When this build was made; used only for pages without a content date of their own. */
const BUILD_TIME = new Date();

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

const LASTMOD = cardLastmod as Record<string, string>;

/** Content date of one card (scripts/update_card_lastmod.py), or null when unknown. */
function cardLastModified(cardId: string): Date | null {
  const raw = LASTMOD[cardId];
  if (!raw) return null;
  const d = new Date(raw);
  return Number.isFinite(d.getTime()) ? d : null;
}

function latest(dates: Array<Date | null | undefined>): Date | null {
  let best: Date | null = null;
  for (const d of dates) {
    if (d && (!best || d.getTime() > best.getTime())) best = d;
  }
  return best;
}

function urlFor(route: string, lang: UrlLang): string {
  return new URL(localizedPath(route, lang), `${SITE_URL}/`).toString();
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const listed = sitemapCardIds(loadCardIds());
  const allCardsDate = latest(listed.map((id) => cardLastModified(id))) ?? BUILD_TIME;

  let leaders: Array<{ leader: string; decks: number; last_date: string }> = [];
  let tournamentsDate: Date | null = null;
  try {
    const res = await fetchLeaders(LEADER_INDEX_MIN_DECKS);
    leaders = (res?.items || []).filter((r) => r.decks >= LEADER_INDEX_MIN_DECKS);
    const synced = res?.synced_at ? new Date(res.synced_at) : null;
    tournamentsDate = synced && Number.isFinite(synced.getTime()) ? synced : null;
  } catch {
    leaders = [];
  }

  const staticRoutes: Array<{
    path: string;
    priority: number;
    changeFrequency: NonNullable<MetadataRoute.Sitemap[number]["changeFrequency"]>;
    lastModified: Date;
    /** Only routes with /en and /zh-hans copies. */
    localized: boolean;
  }> = [
    { path: "/", priority: 1, changeFrequency: "daily", lastModified: allCardsDate, localized: true },
    { path: "/search", priority: 0.98, changeFrequency: "daily", lastModified: allCardsDate, localized: true },
    { path: "/builder", priority: 0.9, changeFrequency: "weekly", lastModified: BUILD_TIME, localized: true },
    {
      path: "/tournaments",
      priority: 0.9,
      changeFrequency: "daily",
      lastModified: tournamentsDate ?? BUILD_TIME,
      localized: true,
    },
    {
      path: "/leaders",
      priority: 0.88,
      changeFrequency: "daily",
      lastModified: tournamentsDate ?? BUILD_TIME,
      localized: true,
    },
    { path: "/collector", priority: 0.8, changeFrequency: "weekly", lastModified: BUILD_TIME, localized: false },
    { path: "/binder", priority: 0.8, changeFrequency: "weekly", lastModified: BUILD_TIME, localized: false },
    { path: "/prices", priority: 0.9, changeFrequency: "daily", lastModified: BUILD_TIME, localized: true },
    { path: "/community", priority: 0.85, changeFrequency: "daily", lastModified: BUILD_TIME, localized: false },
    { path: "/photo", priority: 0.6, changeFrequency: "monthly", lastModified: BUILD_TIME, localized: false },
    { path: "/sets", priority: 0.92, changeFrequency: "weekly", lastModified: allCardsDate, localized: true },
    { path: "/legal/privacy", priority: 0.2, changeFrequency: "yearly", lastModified: BUILD_TIME, localized: false },
    { path: "/legal/terms", priority: 0.2, changeFrequency: "yearly", lastModified: BUILD_TIME, localized: false },
    { path: "/legal/disclaimer", priority: 0.2, changeFrequency: "yearly", lastModified: BUILD_TIME, localized: false },
  ];

  const entries: MetadataRoute.Sitemap = [];
  for (const route of staticRoutes) {
    for (const lang of route.localized ? LANGS : (["zh-Hant"] as UrlLang[])) {
      entries.push({
        url: urlFor(route.path, lang),
        lastModified: route.lastModified,
        changeFrequency: route.changeFrequency,
        priority: lang === "zh-Hant" ? route.priority : Math.max(0.1, route.priority - 0.05),
      });
    }
  }

  for (const set of allSets()) {
    const setDate = latest(set.cards.map((c) => cardLastModified(c.id))) ?? BUILD_TIME;
    for (const lang of LANGS) {
      entries.push({
        url: urlFor(`/sets/${encodeURIComponent(set.code)}`, lang),
        lastModified: setDate,
        changeFrequency: "weekly",
        priority: lang === "zh-Hant" ? 0.85 : 0.8,
      });
    }
  }

  for (const row of leaders) {
    const d = row.last_date ? new Date(`${row.last_date}T00:00:00Z`) : null;
    for (const lang of LANGS) {
      entries.push({
        url: urlFor(`/leaders/${encodeURIComponent(row.leader)}`, lang),
        lastModified: d && Number.isFinite(d.getTime()) ? d : (tournamentsDate ?? BUILD_TIME),
        changeFrequency: "weekly",
        priority: lang === "zh-Hant" ? 0.75 : 0.7,
      });
    }
  }

  let imageCount = 0;
  for (const cardId of listed) {
    const id = normalizeCardId(cardId);
    const base = toBaseCardId(id);
    const isParallel = base !== id;
    const image = sitemapCardImageLoc({ id });
    if (image) imageCount += 1;
    const lastModified = cardLastModified(cardId) ?? BUILD_TIME;
    for (const lang of LANGS) {
      entries.push({
        url: urlFor(`/cards/${encodeURIComponent(cardId)}`, lang),
        lastModified,
        changeFrequency: "weekly",
        priority: (isParallel ? 0.55 : 0.72) - (lang === "zh-Hant" ? 0 : 0.05),
        // The card art is the same file in every language; list it once.
        ...(image && lang === "zh-Hant" ? { images: [image] } : {}),
      });
    }
  }

  const floor = manifestOwnImageCount(listed);
  if (imageCount < floor) {
    throw new Error(
      `sitemap image:loc count ${imageCount} is below ${floor} own manifest hashes`,
    );
  }

  return entries;
}
