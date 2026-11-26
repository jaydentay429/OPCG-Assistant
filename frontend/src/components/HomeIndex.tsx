import Link from "next/link";
import { SITE_URL, faqPageJsonLd, jsonLdScript } from "@/lib/seo";
import { serverCopy } from "@/lib/serverCopy";
import { allSets, setLabel } from "@/lib/sets";
import { formatMetaLabel, loadLatestTournamentMetaKeys } from "@/lib/tournamentMeta";

export async function HomeIndex() {
  const { L, href } = await serverCopy();
  /** Visible homepage FAQ. JSON-LD must use these strings verbatim. */
  const HOME_FAQ = [
    {
      question: L("這是官方網站嗎？", "Is this the official site?"),
      answer: L(
        "不是。本站是粉絲工具，卡名、效果與卡圖屬權利人所有。",
        "No. This is a fan-made tool; card names, effects and artwork belong to their rights holders.",
      ),
    },
    {
      question: L("怎麼查卡？", "How do I look up a card?"),
      answer: L(
        "到 卡牌搜索 輸入卡號或卡名，也可 拍照識卡。",
        "Open Card search and type a card number or name, or use Photo scan.",
      ),
    },
    {
      question: L("可以練牌嗎？", "Can I practise games here?"),
      answer: L(
        "可以。到 即時對戰 用範例卡組對 AI，或開房間。",
        "Yes. Open Play to battle the AI with a sample deck, or open a room.",
      ),
    },
  ] as const;
  const sets = allSets().filter((s) => s.code !== "DON");
  const latestOp = [...sets.filter((s) => s.code.startsWith("OP"))].pop();
  const latestEb = [...sets.filter((s) => s.code.startsWith("EB"))].pop();
  const tournamentSets =
    formatMetaLabel(await loadLatestTournamentMetaKeys()) || L("最新環境", "the latest format");
  const hubs = [
    {
      href: "/search",
      title: L("卡牌搜索", "Card search"),
      body: L("以卡號、卡名、顏色、費用與效果關鍵字查詢全卡表。", "Search every card by number, name, color, cost and effect keywords."),
    },
    {
      href: "/builder",
      title: L("卡組構築", "Deck builder"),
      body: L("線上組 1 領袖 + 50 張，檢查顏色與張數限制。", "Build 1 leader + 50 cards online with color and copy-limit checks."),
    },
    {
      href: "/play",
      title: L("即時對戰", "Live battles"),
      body: L("房間對戰或 AI 練牌；訪客可用範例卡組一鍵開戰。", "Room battles or AI practice; guests can start with a sample deck."),
    },
    {
      href: "/tournaments",
      title: L("賽事卡組", "Tournament decks"),
      body: L(`瀏覽 ${tournamentSets} 等環境 meta deck list。`, `Browse ${tournamentSets} meta deck lists.`),
    },
    {
      href: "/leaders",
      title: L("領袖賽事統計", "Leader stats"),
      body: L("每個領袖的上榜次數、冠軍卡組與常用卡。", "Tournament appearances, champion decks and common cards for each leader."),
    },
    {
      href: "/prices",
      title: L("市場價格", "Market prices"),
      body: L("Yuyu-tei 日圓參考價與走勢。", "Yuyu-tei reference prices in yen, with trends."),
    },
    {
      href: "/photo",
      title: L("拍照識卡", "Photo scan"),
      body: L("上傳或拍攝卡面，辨識卡號後直接看效果。", "Snap or upload a card to identify it and read its effect."),
    },
  ];
  const featured = [
    ...sets.filter((s) => s.code.startsWith("OP")).slice(-8).reverse(),
    ...sets.filter((s) => s.code.startsWith("EB")).slice(-4).reverse(),
    ...sets.filter((s) => s.code.startsWith("ST")).slice(-6).reverse(),
    ...sets.filter((s) => s.code === "P"),
  ];
  const itemList = {
    "@context": "https://schema.org",
    "@type": "ItemList",
    name: L("OPCG 系列卡表", "OPCG set lists"),
    itemListElement: featured.map((s, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: setLabel(s.code),
      url: `${SITE_URL}${href(`/sets/${encodeURIComponent(s.code)}`)}`,
    })),
  };

  const homeFaqLd = faqPageJsonLd(HOME_FAQ.map((item) => ({ question: item.question, answer: item.answer })));

  return (
    <section className="home-index">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLdScript(itemList) }} />
      {homeFaqLd ? (
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: jsonLdScript(homeFaqLd, { allowFaq: true }) }}
        />
      ) : null}
      <h2>{L("航海王卡牌工具箱", "ONE PIECE Card Game toolbox")}</h2>
      <p>
        {L(
          "OPCG 卡牌助手（optcgassistant.com）提供非官方的 ONE PIECE CARD GAME 資料庫、組牌、賽事卡組、市價與瀏覽器練牌。與 BANDAI 無關聯。",
          "OPCG Card Assistant (optcgassistant.com) is an unofficial ONE PIECE CARD GAME database with deck building, tournament decks, market prices and browser practice games. Not affiliated with BANDAI.",
        )}
      </p>
      <ul className="home-index-hubs">
        {hubs.map((h) => (
          <li key={h.href}>
            <Link href={href(h.href)}>
              <strong>{h.title}</strong>
              <span>{h.body}</span>
            </Link>
          </li>
        ))}
      </ul>
      <h2>{L("系列卡表", "Set lists")}</h2>
      <p>
        {L("依彈次瀏覽全卡列表", "Browse every card by set")}
        {latestOp || latestEb ? (
          <>
            {L("，例如", ", for example")}{" "}
            {latestOp ? <Link href={href(`/sets/${latestOp.code}`)}>{setLabel(latestOp.code)}</Link> : null}
            {latestOp && latestEb ? L("、", ", ") : null}
            {latestEb ? <Link href={href(`/sets/${latestEb.code}`)}>{setLabel(latestEb.code)}</Link> : null}
          </>
        ) : null}
        {L("。", ".")}
        <Link href={href("/sets")}>{L(" 看全部系列 →", " All sets →")}</Link>
      </p>
      <ul className="home-index-sets">
        {featured.map((s) => (
          <li key={s.code}>
            <Link href={href(`/sets/${encodeURIComponent(s.code)}`)}>
              {setLabel(s.code)}
              <span className="muted"> {s.count}</span>
            </Link>
          </li>
        ))}
      </ul>
      <h2>{L("常見問題", "FAQ")}</h2>
      <dl className="home-index-faq">
        <dt>{HOME_FAQ[0].question}</dt>
        <dd>{HOME_FAQ[0].answer}</dd>
        <dt>{HOME_FAQ[1].question}</dt>
        <dd>
          {L("到", "Open")} <Link href={href("/search")}>{L("卡牌搜索", "Card search")}</Link>{" "}
          {L("輸入卡號或卡名，也可", "and type a card number or name, or use")}{" "}
          <Link href="/photo">{L("拍照識卡", "Photo scan")}</Link>
          {L("。", ".")}
        </dd>
        <dt>{HOME_FAQ[2].question}</dt>
        <dd>
          {L("可以。到", "Yes. Open")} <Link href="/play">{L("即時對戰", "Play")}</Link>{" "}
          {L("用範例卡組對 AI，或開房間。", "to battle the AI with a sample deck, or open a room.")}
        </dd>
      </dl>
    </section>
  );
}
