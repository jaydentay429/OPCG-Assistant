import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { JsonLd } from "@/components/JsonLd";
import { TournamentDecksPageClient } from "@/components/TournamentDecksPageClient";
import { fetchTopdecksDecks } from "@/lib/api";
import { BRAND_KEYWORDS, buildPageMetadata, breadcrumbJsonLd } from "@/lib/seo";
import {
  loadLatestTournamentMetaKeys,
  tournamentDocumentTitle,
  tournamentMetaKeywords,
  tournamentPageDescription,
  tournamentSeoIntro,
} from "@/lib/tournamentMeta";

export const revalidate = 3600;

export async function generateMetadata(): Promise<Metadata> {
  const keys = await loadLatestTournamentMetaKeys();
  return buildPageMetadata({
    title: tournamentDocumentTitle("zh-Hant", keys),
    description: tournamentPageDescription("zh-Hant", keys),
    path: "/tournaments",
    absoluteTitle: true,
    keywords: [...BRAND_KEYWORDS, ...tournamentMetaKeywords(keys)],
  });
}

export default async function TournamentsPage() {
  const keys = await loadLatestTournamentMetaKeys();
  let decks: Awaited<ReturnType<typeof fetchTopdecksDecks>>["items"] = [];
  try {
    const res = await fetchTopdecksDecks({ limit: 8, offset: 0 });
    decks = res.items || [];
  } catch {
    decks = [];
  }

  return (
    <>
      <JsonLd
        data={breadcrumbJsonLd([
          { name: "Home", path: "/" },
          { name: "Tournament deck lists", path: "/tournaments" },
        ])}
      />
      <section className="page-seo-intro seo-only" aria-hidden="true">
        <p>{tournamentSeoIntro(keys)}</p>
        {decks.length ? (
          <ol className="seo-public-list">
            {decks.map((row) => {
              const leader = row.leader_name || row.leader || "領袖";
              const meta = row.meta_title || row.format || "賽事";
              const href = `/tournaments?deck=${encodeURIComponent(row.id)}`;
              return (
                <li key={row.id}>
                  <Link href={href}>
                    {meta} · {leader}
                  </Link>
                </li>
              );
            })}
          </ol>
        ) : null}
      </section>
      <Suspense fallback={<p className="muted">…</p>}>
        <TournamentDecksPageClient />
      </Suspense>
    </>
  );
}
