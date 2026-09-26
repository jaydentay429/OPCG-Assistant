import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { JsonLd } from "@/components/JsonLd";
import { TournamentDecksPageClient } from "@/components/TournamentDecksPageClient";
import { fetchTopdecksDecks } from "@/lib/api";
import { BRAND_KEYWORDS, buildPageMetadata, breadcrumbJsonLd } from "@/lib/seo";

export const metadata: Metadata = buildPageMetadata({
  title: "OP17 / OP16 Deck List 賽事卡組 | OPCG Assistant 比賽卡組瀏覽",
  description:
    "Browse ONE PIECE CARD GAME tournament deck lists on optcgassistant.com：查看 OP17、OP16、EB 等環境賽事卡組，研究 meta deck，並可一鍵導入到 OPCG Assistant 卡組構築與對戰練習。",
  path: "/tournaments",
  absoluteTitle: true,
  keywords: [
    ...BRAND_KEYWORDS,
    "OP17 deck list",
    "OP16 deck list",
    "OP-17 decklist",
    "ONE PIECE TCG tournament decks",
    "OPCG meta",
    "賽事卡組",
    "比赛卡组",
  ],
});

export default async function TournamentsPage() {
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
        <p>
          在 optcgassistant.com 瀏覽 ONE PIECE CARD GAME 公開賽事卡組：依環境（如 OP17、OP16）、領袖與比賽篩選，並可導入卡組構築與對戰練習。列表會隨資料更新。
        </p>
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
