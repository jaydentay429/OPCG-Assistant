import Link from "next/link";
import { SITE_URL, jsonLdScript } from "@/lib/seo";
import { allSets, setLabel } from "@/lib/sets";

const HUBS = [
  { href: "/search", title: "卡牌搜索", body: "以卡號、卡名、顏色、費用與效果關鍵字查詢全卡表。" },
  { href: "/builder", title: "卡組構築", body: "線上組 1 領袖 + 50 張，檢查顏色與張數限制。" },
  { href: "/play", title: "即時對戰", body: "房間對戰或 AI 練牌；訪客可用範例卡組一鍵開戰。" },
  { href: "/tournaments", title: "賽事卡組", body: "瀏覽 OP17 / OP16 等環境 meta deck list。" },
  { href: "/prices", title: "市場價格", body: "Yuyu-tei 日圓參考價與走勢。" },
  { href: "/photo", title: "拍照識卡", body: "上傳或拍攝卡面，辨識卡號後直接看效果。" },
];

export function HomeIndex() {
  const sets = allSets().filter((s) => s.code !== "DON");
  const featured = [
    ...sets.filter((s) => s.code.startsWith("OP")).slice(-8).reverse(),
    ...sets.filter((s) => s.code.startsWith("EB")).slice(-4).reverse(),
    ...sets.filter((s) => s.code.startsWith("ST")).slice(-6).reverse(),
    ...sets.filter((s) => s.code === "P"),
  ];
  const itemList = {
    "@context": "https://schema.org",
    "@type": "ItemList",
    name: "OPCG 系列卡表",
    itemListElement: featured.map((s, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: setLabel(s.code),
      url: `${SITE_URL}/sets/${encodeURIComponent(s.code)}`,
    })),
  };

  return (
    <section className="home-index">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLdScript(itemList) }} />
      <h2>航海王卡牌工具箱</h2>
      <p>
        OPCG 卡牌助手（optcgassistant.com）提供非官方的 ONE PIECE CARD GAME
        資料庫、組牌、賽事卡組、市價與瀏覽器練牌。與 BANDAI 無關聯。
      </p>
      <ul className="home-index-hubs">
        {HUBS.map((h) => (
          <li key={h.href}>
            <Link href={h.href}>
              <strong>{h.title}</strong>
              <span>{h.body}</span>
            </Link>
          </li>
        ))}
      </ul>
      <h2>系列卡表</h2>
      <p>
        依彈次瀏覽全卡列表，例如{" "}
        <Link href="/sets/OP18">OP-18</Link>、<Link href="/sets/EB05">EB-05</Link>。
        <Link href="/sets"> 看全部系列 →</Link>
      </p>
      <ul className="home-index-sets">
        {featured.map((s) => (
          <li key={s.code}>
            <Link href={`/sets/${encodeURIComponent(s.code)}`}>
              {setLabel(s.code)}
              <span className="muted"> {s.count}</span>
            </Link>
          </li>
        ))}
      </ul>
      <h2>常見問題</h2>
      <dl className="home-index-faq">
        <dt>這是官方網站嗎？</dt>
        <dd>不是。本站是粉絲工具，卡名、效果與卡圖屬權利人所有。</dd>
        <dt>怎麼查卡？</dt>
        <dd>
          到 <Link href="/search">卡牌搜索</Link> 輸入卡號或卡名，也可{" "}
          <Link href="/photo">拍照識卡</Link>。
        </dd>
        <dt>可以練牌嗎？</dt>
        <dd>
          可以。到 <Link href="/play">即時對戰</Link> 用範例卡組對 AI，或開房間。
        </dd>
      </dl>
    </section>
  );
}
