import type { Metadata } from "next";
import Link from "next/link";
import { breadcrumbJsonLd, buildPageMetadata, jsonLdScript } from "@/lib/seo";
import { allSets, setLabel } from "@/lib/sets";

export const metadata: Metadata = buildPageMetadata({
  title: "OPCG 系列卡表總覽｜OP / EB / ST / P",
  description:
    "依彈次瀏覽 ONE PIECE CARD GAME 全卡表：OP 補充包、EB Extra Booster、ST 起始牌組與 P 宣傳卡，點進每張卡查看效果與價格。",
  path: "/sets",
  absoluteTitle: true,
  keywords: ["OPCG 卡表", "OP18 卡表", "EB05 卡表", "航海王卡牌系列", "ONE PIECE CARD GAME set list"],
});

export default function SetsIndexPage() {
  const sets = allSets().filter((s) => s.code !== "DON");
  const groups = [
    { key: "OP", title: "補充包 OP", items: sets.filter((s) => s.code.startsWith("OP")).reverse() },
    { key: "EB", title: "Extra Booster EB", items: sets.filter((s) => s.code.startsWith("EB")).reverse() },
    { key: "ST", title: "起始牌組 ST", items: sets.filter((s) => s.code.startsWith("ST")).reverse() },
    { key: "P", title: "宣傳卡", items: sets.filter((s) => s.code === "P") },
  ];

  return (
    <div className="stack set-index-page">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: jsonLdScript(
            breadcrumbJsonLd([
              { name: "首頁", path: "/" },
              { name: "系列卡表", path: "/sets" },
            ]),
          ),
        }}
      />
      <h1 className="page-title">系列卡表</h1>
      <p className="muted">
        全系列 ONE PIECE CARD GAME 卡號列表。選彈次即可查看該包全部卡牌，並連到效果、價格與組牌。
      </p>
      {groups.map((g) =>
        g.items.length ? (
          <section key={g.key}>
            <h2>{g.title}</h2>
            <ul className="home-index-sets">
              {g.items.map((s) => (
                <li key={s.code}>
                  <Link href={`/sets/${encodeURIComponent(s.code)}`}>
                    {setLabel(s.code)}
                    <span className="muted"> {s.count} 張</span>
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
