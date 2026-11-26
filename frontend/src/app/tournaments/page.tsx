import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { JsonLd } from "@/components/JsonLd";
import { TournamentDecksPageClient } from "@/components/TournamentDecksPageClient";
import { fetchTopdecksDecks } from "@/lib/api";
import { toBaseCardId } from "@/lib/cardId";
import { BRAND_KEYWORDS, buildPageMetadata, breadcrumbJsonLd } from "@/lib/seo";
import { serverCopy } from "@/lib/serverCopy";
import {
  loadLatestTournamentMetaKeys,
  tournamentDocumentTitle,
  tournamentMetaKeywords,
  tournamentPageDescription,
  tournamentSeoIntro,
} from "@/lib/tournamentMeta";

export async function generateMetadata(): Promise<Metadata> {
  const { lang } = await serverCopy();
  const keys = await loadLatestTournamentMetaKeys();
  return buildPageMetadata({
    title: tournamentDocumentTitle(lang, keys),
    description: tournamentPageDescription(lang, keys),
    path: "/tournaments",
    absoluteTitle: true,
    lang,
    keywords: [...BRAND_KEYWORDS, ...tournamentMetaKeywords(keys)],
  });
}

export default async function TournamentsPage() {
  const { lang, L, href, hans } = await serverCopy();
  const keys = await loadLatestTournamentMetaKeys();
  let decks: Awaited<ReturnType<typeof fetchTopdecksDecks>>["items"] = [];
  try {
    const res = await fetchTopdecksDecks({ limit: 8, offset: 0 });
    decks = res.items || [];
  } catch {
    decks = [];
  }
  const intro =
    lang === "en" ? tournamentPageDescription("en", keys) : L(tournamentSeoIntro(keys), "");

  return (
    <>
      <JsonLd
        data={breadcrumbJsonLd([
          { name: L("首頁", "Home"), path: href("/") },
          { name: L("賽事卡組", "Tournament deck lists"), path: href("/tournaments") },
        ])}
      />
      <section className="page-seo-intro seo-only" aria-hidden="true">
        <p>{intro}</p>
        <p>
          <Link href={href("/leaders")}>{L("各領袖上榜次數、冠軍卡組與常用卡", "Leader stats: appearances, champion decks and common cards")}</Link>
        </p>
        {decks.length ? (
          <ol className="seo-public-list">
            {decks.map((row) => {
              const leaderName =
                lang === "en"
                  ? row.leader_name_en || row.leader || "Leader"
                  : hans(row.leader_name || row.leader || "領袖");
              const meta = row.meta_title || row.format || L("賽事", "Tournament");
              const deckHref = `${href("/tournaments")}?deck=${encodeURIComponent(row.id)}`;
              return (
                <li key={row.id}>
                  <Link href={deckHref}>
                    {meta} · {leaderName}
                  </Link>
                  {row.leader ? (
                    <>
                      {" · "}
                      <Link href={href(`/leaders/${encodeURIComponent(toBaseCardId(row.leader))}`)}>
                        {L("領袖統計", "Leader stats")}
                      </Link>
                    </>
                  ) : null}
                </li>
              );
            })}
          </ol>
        ) : null}
      </section>
      {/* Reserve the viewport while the client list loads so the footer does not jump (CLS). */}
      <div className="route-fill">
        <Suspense fallback={<p className="muted">…</p>}>
          <TournamentDecksPageClient />
        </Suspense>
      </div>
    </>
  );
}
