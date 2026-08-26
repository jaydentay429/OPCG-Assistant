import type { Metadata } from "next";
import { Suspense } from "react";
import { TournamentDecksPageClient } from "@/components/TournamentDecksPageClient";
import { BRAND_KEYWORDS, buildPageMetadata, breadcrumbJsonLd, jsonLdScript } from "@/lib/seo";

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

export default function TournamentsPage() {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: jsonLdScript(
            breadcrumbJsonLd([
              { name: "Home", path: "/" },
              { name: "Tournament deck lists", path: "/tournaments" },
            ]),
          ),
        }}
      />
      {/* Keyword copy for crawlers; page title comes from the client UI. */}
      <section className="page-seo-intro seo-only" aria-hidden="true">
        <h1>OP17 / OP16 Deck List · 賽事卡組</h1>
        <p>
          在 optcgassistant.com（OPCG Assistant）瀏覽 ONE PIECE CARD GAME 賽事卡組與 meta deck list：依環境（如
          OP17、OP16）、領袖、國家與比賽篩選，並可導入到卡組構築與即時對戰練習。
        </p>
        <p>
          Browse tournament deck lists for OPCG / OPTCG — including OP17 and OP16 formats — then import builds into
          the deck builder.
        </p>
      </section>
      <Suspense fallback={<p className="muted">…</p>}>
        <TournamentDecksPageClient />
      </Suspense>
    </>
  );
}
