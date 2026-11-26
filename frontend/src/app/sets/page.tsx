import type { Metadata } from "next";
import Link from "next/link";
import { breadcrumbJsonLd, buildPageMetadata, jsonLdScript } from "@/lib/seo";
import { serverCopy } from "@/lib/serverCopy";
import { allSets, setLabel, setLabelEn } from "@/lib/sets";

export async function generateMetadata(): Promise<Metadata> {
  const { lang, L } = await serverCopy();
  return buildPageMetadata({
    title: L("OPCG 系列卡表總覽｜OP / EB / ST / P", "OPCG Set Lists | OP / EB / ST / Promo"),
    description: L(
      "依彈次瀏覽 ONE PIECE CARD GAME 全卡表：OP 補充包、EB Extra Booster、ST 起始牌組與 P 宣傳卡，點進每張卡查看效果與價格。",
      "Browse every ONE PIECE CARD GAME set: OP booster packs, EB Extra Boosters, ST starter decks and P promos. Open any card for its effect and price.",
    ),
    path: "/sets",
    absoluteTitle: true,
    lang,
    keywords: [
      L("OPCG 卡表", "OPCG card list"),
      L("OP18 卡表", "OP18 card list"),
      L("EB05 卡表", "EB05 card list"),
      L("航海王卡牌系列", "ONE PIECE TCG sets"),
      "ONE PIECE CARD GAME set list",
    ],
  });
}

export default async function SetsIndexPage() {
  const { lang, L, href } = await serverCopy();
  const label = (code: string) => (lang === "en" ? setLabelEn(code) : setLabel(code));
  const sets = allSets().filter((s) => s.code !== "DON");
  const groups = [
    { key: "OP", title: L("補充包 OP", "Booster packs (OP)"), items: sets.filter((s) => s.code.startsWith("OP")).reverse() },
    { key: "EB", title: "Extra Booster EB", items: sets.filter((s) => s.code.startsWith("EB")).reverse() },
    { key: "ST", title: L("起始牌組 ST", "Starter decks (ST)"), items: sets.filter((s) => s.code.startsWith("ST")).reverse() },
    { key: "P", title: L("宣傳卡", "Promos"), items: sets.filter((s) => s.code === "P") },
  ];

  return (
    <div className="stack set-index-page">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: jsonLdScript(
            breadcrumbJsonLd([
              { name: L("首頁", "Home"), path: href("/") },
              { name: L("系列卡表", "Set lists"), path: href("/sets") },
            ]),
          ),
        }}
      />
      <h1 className="page-title">{L("系列卡表", "Set lists")}</h1>
      <p className="muted">
        {L(
          "全系列 ONE PIECE CARD GAME 卡號列表。選彈次即可查看該包全部卡牌，並連到效果、價格與組牌。",
          "Card number lists for every ONE PIECE CARD GAME set. Pick a set to see all of its cards, with links to effects, prices and deck building.",
        )}
      </p>
      {groups.map((g) =>
        g.items.length ? (
          <section key={g.key}>
            <h2>{g.title}</h2>
            <ul className="home-index-sets">
              {g.items.map((s) => (
                <li key={s.code}>
                  <Link href={href(`/sets/${encodeURIComponent(s.code)}`)}>
                    {label(s.code)}
                    <span className="muted">{L(` ${s.count} 張`, ` ${s.count} cards`)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ) : null,
      )}
    </div>
  );
}
