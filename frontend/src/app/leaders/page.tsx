import type { Metadata } from "next";
import Link from "next/link";
import { JsonLd } from "@/components/JsonLd";
import { displayCardId } from "@/lib/cardId";
import {
  LEADER_INDEX_MIN_DECKS,
  fetchLeaders,
  formatLeaderDate,
  leaderDisplayName,
  type LeaderList,
} from "@/lib/leaders";
import { SITE_URL, breadcrumbJsonLd, buildPageMetadata } from "@/lib/seo";
import { serverCopy } from "@/lib/serverCopy";

export async function generateMetadata(): Promise<Metadata> {
  const { lang, L } = await serverCopy();
  return buildPageMetadata({
    title: L(
      "OPCG 領袖賽事統計｜各領袖上榜次數、冠軍卡組與常用卡",
      "OPCG Leader Stats | Tournament Appearances, Champion Decks and Common Cards",
    ),
    description: L(
      "依公開賽事卡組統計每個 ONE PIECE CARD GAME 領袖：上榜次數、冠軍次數、最近出賽日期，點進領袖可看冠軍卡組與常用卡。",
      "Every ONE PIECE CARD GAME leader ranked by public tournament results: appearances, wins and latest date. Open a leader for champion decks and the most played cards.",
    ),
    path: "/leaders",
    absoluteTitle: true,
    lang,
    keywords: [
      L("OPCG 領袖", "OPCG leaders"),
      L("領袖勝率", "OPTCG leader tier list"),
      L("賽事卡組", "tournament decks"),
      "ONE PIECE CARD GAME meta",
    ],
  });
}

export default async function LeadersPage() {
  const { lang, L, href } = await serverCopy();
  let data: LeaderList | null = null;
  try {
    data = await fetchLeaders(1);
  } catch {
    data = null;
  }
  const rows = (data?.items || []).filter((r) => r.decks >= LEADER_INDEX_MIN_DECKS);
  const small = (data?.items || []).length - rows.length;
  const listLd = {
    "@context": "https://schema.org",
    "@type": "ItemList",
    name: L("OPCG 領袖賽事統計", "OPCG leader stats"),
    numberOfItems: rows.length,
    itemListElement: rows.slice(0, 100).map((r, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: `${leaderDisplayName(r, lang)} (${displayCardId(r.leader)})`,
      url: `${SITE_URL}${href(`/leaders/${encodeURIComponent(r.leader)}`)}`,
    })),
  };

  return (
    <div className="stack leaders-page">
      <JsonLd
        data={[
          breadcrumbJsonLd([
            { name: L("首頁", "Home"), path: href("/") },
            { name: L("賽事卡組", "Tournament decks"), path: href("/tournaments") },
            { name: L("領袖賽事統計", "Leader stats"), path: href("/leaders") },
          ]),
          listLd,
        ]}
      />
      <nav className="set-page-nav muted">
        <Link href={href("/tournaments")}>{L("賽事卡組", "Tournament decks")}</Link>
        {" / "}
        <span>{L("領袖賽事統計", "Leader stats")}</span>
      </nav>
      <h1 className="page-title">{L("領袖賽事統計", "Leader tournament stats")}</h1>
      <p className="muted">
        {data
          ? L(
              `統計 ${data.total_decks} 套公開賽事卡組（資料來源 ONE PIECE TOP DECKS）。列出至少 ${LEADER_INDEX_MIN_DECKS} 套上榜的 ${rows.length} 個領袖，依上榜次數排序。`,
              `Based on ${data.total_decks} public tournament deck lists (source: ONE PIECE TOP DECKS). ${rows.length} leaders with at least ${LEADER_INDEX_MIN_DECKS} decks, most appearances first.`,
            )
          : L("賽事資料暫時無法載入，請稍後再試。", "Tournament data is unavailable right now. Please try again later.")}
        {small > 0
          ? L(` 另有 ${small} 個領袖上榜少於 ${LEADER_INDEX_MIN_DECKS} 套。`, ` ${small} more leaders have fewer than ${LEADER_INDEX_MIN_DECKS} decks.`)
          : ""}
      </p>
      {rows.length ? (
        <div className="leader-table-wrap">
          <table className="leader-table">
            <thead>
              <tr>
                <th scope="col">#</th>
                <th scope="col">{L("領袖", "Leader")}</th>
                <th scope="col">{L("上榜", "Decks")}</th>
                <th scope="col">{L("冠軍", "Wins")}</th>
                <th scope="col">{L("最近", "Latest")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={r.leader}>
                  <td>{i + 1}</td>
                  <td>
                    <Link href={href(`/leaders/${encodeURIComponent(r.leader)}`)}>
                      <span className="set-card-id">{displayCardId(r.leader)}</span> {leaderDisplayName(r, lang)}
                    </Link>
                  </td>
                  <td>{r.decks}</td>
                  <td>{r.wins}</td>
                  <td>{formatLeaderDate(r.last_date, lang)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
