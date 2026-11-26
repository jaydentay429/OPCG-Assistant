import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { CardImg } from "@/components/CardImg";
import { JsonLd } from "@/components/JsonLd";
import type { TopdeckBrief } from "@/lib/api";
import { displayCardId, normalizeCardId, toBaseCardId } from "@/lib/cardId";
import {
  fetchLeader,
  formatLeaderDate,
  leaderDisplayName,
  leaderIsIndexable,
  topdeckDateIso,
  type LeaderDetail,
} from "@/lib/leaders";
import { SITE_URL, breadcrumbJsonLd, buildPageMetadata, cardOgImage } from "@/lib/seo";
import { serverCopy, type ServerCopy } from "@/lib/serverCopy";
import { displayKeepingParens, pickFacetLabel } from "@/lib/topdeckLocale";

type LoadResult = { kind: "ok"; data: LeaderDetail } | { kind: "missing" } | { kind: "error" };

async function load(rawId: string): Promise<LoadResult> {
  try {
    const data = await fetchLeader(rawId);
    return data ? { kind: "ok", data } : { kind: "missing" };
  } catch {
    return { kind: "error" };
  }
}

function leaderIdFrom(raw: string): string {
  let text = raw;
  try {
    text = decodeURIComponent(raw);
  } catch {
    /* keep */
  }
  return toBaseCardId(normalizeCardId(text));
}

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id: raw } = await params;
  const id = leaderIdFrom(raw);
  const { lang, L } = await serverCopy();
  const res = await load(id);
  const path = `/leaders/${encodeURIComponent(id)}`;
  if (res.kind !== "ok") {
    return {
      ...buildPageMetadata({
        title: L(`${displayCardId(id)} 領袖賽事統計`, `${displayCardId(id)} leader stats`),
        description: L("找不到這個領袖的賽事卡組。", "No tournament decks for this leader."),
        path,
        lang,
        noIndex: true,
      }),
    };
  }
  const d = res.data;
  const name = leaderDisplayName(d, lang);
  const img = cardOgImage(d.leader);
  return buildPageMetadata({
    title: L(
      `${name}（${displayCardId(d.leader)}）領袖賽事統計｜${d.decks} 套上榜、${d.wins} 次冠軍`,
      `${name} (${displayCardId(d.leader)}) Leader Stats | ${d.decks} Tournament Decks, ${d.wins} Wins`,
    ),
    description: L(
      `${name}（${displayCardId(d.leader)}）在公開賽事中上榜 ${d.decks} 次、奪冠 ${d.wins} 次，最近一次 ${formatLeaderDate(d.last_date, "zh-Hant")}。查看冠軍卡組與 ${d.sample_decks} 套近期卡組的常用卡與平均張數。`,
      `${name} (${displayCardId(d.leader)}) has ${d.decks} public tournament decks and ${d.wins} wins, latest on ${formatLeaderDate(d.last_date, "en")}. See champion decks and the most played cards with average copies from ${d.sample_decks} recent decks.`,
    ),
    path,
    absoluteTitle: true,
    lang,
    type: "article",
    images: img ? [img] : undefined,
    noIndex: !leaderIsIndexable(d),
    keywords: [name, d.name_en, displayCardId(d.leader), L("領袖", "leader"), L("賽事卡組", "deck list"), "OPCG"].filter(
      Boolean,
    ) as string[],
  });
}

function deckRow(copy: ServerCopy, row: TopdeckBrief) {
  const { lang, href, L } = copy;
  const placement = displayKeepingParens(lang, row.placement, row.placement_key, row.placement_labels) || row.placement || "";
  const tournament =
    pickFacetLabel(lang, row.tournament_key || "", row.tournament_labels) || row.tournament || "";
  const iso = topdeckDateIso(row.date);
  return (
    <tr key={row.id}>
      <td>{iso ? formatLeaderDate(iso, lang) : row.date || "-"}</td>
      <td>{placement || "-"}</td>
      <td>{tournament && tournament !== row.tournament_key ? tournament : row.tournament || "-"}</td>
      <td>{row.author || "-"}</td>
      <td>
        <Link href={`${href("/tournaments")}?deck=${encodeURIComponent(String(row.id || ""))}`}>
          {L("看卡組", "View deck")}
        </Link>
      </td>
    </tr>
  );
}

function DeckTable({ copy, rows }: { copy: ServerCopy; rows: TopdeckBrief[] }) {
  const { L } = copy;
  return (
    <div className="leader-table-wrap">
      <table className="leader-table">
        <thead>
          <tr>
            <th scope="col">{L("日期", "Date")}</th>
            <th scope="col">{L("名次", "Placement")}</th>
            <th scope="col">{L("賽事", "Tournament")}</th>
            <th scope="col">{L("玩家", "Player")}</th>
            <th scope="col">
              <span className="sr-only">{L("連結", "Link")}</span>
            </th>
          </tr>
        </thead>
        <tbody>{rows.map((row) => deckRow(copy, row))}</tbody>
      </table>
    </div>
  );
}

export default async function LeaderPage({ params }: { params: Promise<{ id: string }> }) {
  const { id: raw } = await params;
  const id = leaderIdFrom(raw);
  const copy = await serverCopy();
  const { lang, L, href } = copy;
  const res = await load(id);
  if (res.kind === "missing") notFound();
  if (res.kind === "error") {
    return (
      <div className="stack" role="status">
        <h1 className="page-title">{L("領袖統計暫時無法載入", "Leader stats are unavailable")}</h1>
        <p className="muted">{L("賽事資料服務暫時沒有回應，請稍後再試。", "The tournament data service did not answer. Please try again later.")}</p>
        <p>
          <Link href={href("/leaders")}>{L("回到領袖列表", "Back to all leaders")}</Link>
        </p>
      </div>
    );
  }
  const d = res.data;
  const name = leaderDisplayName(d, lang);
  const shownId = displayCardId(d.leader);
  const pageUrl = `${SITE_URL}${href(`/leaders/${encodeURIComponent(d.leader)}`)}`;
  const jp = Number(d.formats?.jp || 0);
  const en = Number(d.formats?.en || 0);
  const cardName = (c: { name: string; name_hans: string; name_en: string; id: string }) =>
    lang === "en" ? c.name_en || c.name || c.id : lang === "zh-Hans" ? c.name_hans || c.name : c.name;

  const ld = {
    "@context": "https://schema.org",
    "@type": "Dataset",
    name: L(`${name}（${shownId}）領袖賽事統計`, `${name} (${shownId}) leader tournament stats`),
    description: L(
      `${name} 在 ${d.decks} 套公開賽事卡組中的上榜、冠軍與常用卡統計。`,
      `Appearances, wins and common cards for ${name} across ${d.decks} public tournament decks.`,
    ),
    url: pageUrl,
    inLanguage: lang,
    dateModified: d.last_date || undefined,
    creator: { "@type": "Organization", name: "OPCG Card Assistant", url: SITE_URL },
    isBasedOn: "https://onepiecetopdecks.com/deck-list/",
  };

  return (
    <div className="stack leader-page">
      <JsonLd
        data={[
          breadcrumbJsonLd([
            { name: L("首頁", "Home"), path: href("/") },
            { name: L("領袖賽事統計", "Leader stats"), path: href("/leaders") },
            { name: `${name} (${shownId})`, path: href(`/leaders/${encodeURIComponent(d.leader)}`) },
          ]),
          ld,
        ]}
      />
      <nav className="set-page-nav muted">
        <Link href={href("/leaders")}>{L("領袖賽事統計", "Leader stats")}</Link>
        {" / "}
        <span>{shownId}</span>
      </nav>
      <div className="leader-head">
        <Link href={href(`/cards/${encodeURIComponent(d.leader)}`)} className="leader-head-img">
          <CardImg cardId={d.leader} alt={`${name} ${shownId}`} listThumb imageSizes="120px" loading="eager" fetchPriority="high" />
        </Link>
        <div>
          <h1 className="page-title">
            {L(`${name}（${shownId}）領袖賽事統計`, `${name} (${shownId}) leader stats`)}
          </h1>
          <dl className="leader-stats">
            <dt>{L("上榜卡組", "Tournament decks")}</dt>
            <dd>{d.decks}</dd>
            <dt>{L("冠軍", "Wins")}</dt>
            <dd>{d.wins}</dd>
            <dt>{L("前四／八強", "Top 4 / Top 8")}</dt>
            <dd>{d.top_finishes}</dd>
            <dt>{L("日本／亞洲・英文版", "Japan/Asia · English")}</dt>
            <dd>
              {jp} · {en}
            </dd>
            <dt>{L("出賽期間", "Seen")}</dt>
            <dd>
              {formatLeaderDate(d.first_date, lang)} – {formatLeaderDate(d.last_date, lang)}
            </dd>
          </dl>
          <p>
            <Link href={href(`/cards/${encodeURIComponent(d.leader)}`)}>{L("看領袖卡效果與價格 →", "Card effect and price →")}</Link>
          </p>
        </div>
      </div>

      <section>
        <h2>{L("冠軍卡組", "Champion decks")}</h2>
        {d.champion_decks.length ? (
          <DeckTable copy={copy} rows={d.champion_decks} />
        ) : (
          <p className="muted">{L("目前沒有冠軍紀錄。", "No tournament wins recorded yet.")}</p>
        )}
      </section>

      <section>
        <h2>{L("常用卡", "Most played cards")}</h2>
        <p className="muted">
          {L(
            `依最近 ${d.sample_decks} 套上榜卡組統計：採用率＝放入這張卡的卡組比例，平均張數只算有放的卡組。`,
            `From the ${d.sample_decks} most recent tournament decks: play rate is the share of decks running the card; average copies counts only those decks.`,
          )}
        </p>
        <div className="leader-table-wrap">
          <table className="leader-table">
            <thead>
              <tr>
                <th scope="col">{L("卡牌", "Card")}</th>
                <th scope="col">{L("採用率", "Play rate")}</th>
                <th scope="col">{L("平均張數", "Avg. copies")}</th>
              </tr>
            </thead>
            <tbody>
              {d.common_cards.map((c) => (
                <tr key={c.id}>
                  <td>
                    <Link href={href(`/cards/${encodeURIComponent(c.id)}`)}>
                      <span className="set-card-id">{displayCardId(c.id)}</span> {cardName(c)}
                    </Link>
                  </td>
                  <td>{Math.round(c.rate * 100)}%</td>
                  <td>{c.avg_qty.toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2>{L("最近上榜", "Recent decks")}</h2>
        <DeckTable copy={copy} rows={d.recent_decks} />
      </section>
      <p className="muted">
        {L("資料來源：ONE PIECE TOP DECKS 公開賽事卡組。", "Source: public tournament deck lists from ONE PIECE TOP DECKS.")}
      </p>
    </div>
  );
}
