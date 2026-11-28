import type { Metadata } from "next";
import Link from "next/link";
import { JsonLd } from "@/components/JsonLd";
import { BEGINNER_GUIDE, BEGINNER_GUIDE_VERSION } from "@/lib/beginnerGuide";
import { breadcrumbJsonLd, buildPageMetadata } from "@/lib/seo";
import { serverCopy } from "@/lib/serverCopy";

export async function generateMetadata(): Promise<Metadata> {
  const { lang, L } = await serverCopy();
  return buildPageMetadata({
    title: L(
      "OPCG 新手入門｜航海王卡牌對戰規則一頁看懂",
      "OPCG Beginner Guide | ONE PIECE CARD GAME Rules in One Page",
    ),
    description: L(
      "依官方規則手冊整理：勝利條件、卡組準備、場地區域、回合流程與戰鬥 5 步驟，新手第一次對戰前讀這一頁就夠。",
      "Based on the official rule manual: how to win, deck setup, play areas, turn flow and the 5 battle steps. Everything a new ONE PIECE CARD GAME player needs for a first match.",
    ),
    path: "/beginner",
    absoluteTitle: true,
    lang,
    keywords: [
      L("OPCG 新手", "OPCG beginner"),
      L("航海王卡牌規則", "ONE PIECE CARD GAME rules"),
      L("OPCG 怎麼玩", "how to play OPTCG"),
    ],
  });
}

export default async function BeginnerPage() {
  const { L, href } = await serverCopy();
  return (
    <div className="stack beginner-page">
      <JsonLd
        data={[
          breadcrumbJsonld(L, href),
        ]}
      />
      <nav className="set-page-nav muted">
        <Link href={href("/")}>{L("首頁", "Home")}</Link>
        {" / "}
        <span>{L("新手入門", "Beginner guide")}</span>
      </nav>
      <h1 className="page-title">{L("OPCG 新手入門", "OPCG beginner guide")}</h1>
      <p className="muted">
        {L(
          `依據官方規則指導手冊 ${BEGINNER_GUIDE_VERSION} 整理。規則手冊與卡牌文字有矛盾時，以卡牌文字為優先。`,
          `Based on the official Rule Guidance Manual ${BEGINNER_GUIDE_VERSION}. If the manual and a card's text disagree, the card text takes priority.`,
        )}
      </p>
      <nav className="muted" aria-label={L("本頁目錄", "On this page")}>
        {BEGINNER_GUIDE.map((s, i) => (
          <span key={s.id}>
            {i ? " · " : ""}
            <a href={`#${s.id}`}>{L(s.title.hant, s.title.en)}</a>
          </span>
        ))}
      </nav>
      {BEGINNER_GUIDE.map((s) => {
        const lines = s.items.map((it) => L(it.hant, it.en));
        return (
          <section key={s.id} id={s.id} className="stack">
            <h2>{L(s.title.hant, s.title.en)}</h2>
            {s.kind === "p" ? lines.map((t) => <p key={t}>{t}</p>) : null}
            {s.kind === "ul" ? (
              <ul>
                {lines.map((t) => (
                  <li key={t}>{t}</li>
                ))}
              </ul>
            ) : null}
            {s.kind === "ol" ? (
              <ol>
                {lines.map((t) => (
                  <li key={t}>{t}</li>
                ))}
              </ol>
            ) : null}
          </section>
        );
      })}
      <p>
        <Link href={href("/builder")}>{L("去組一副卡組", "Build a deck")}</Link>
        {" · "}
        <Link href={href("/search")}>{L("查卡", "Search cards")}</Link>
      </p>
    </div>
  );
}

function breadcrumbJsonld(L: (a: string, b: string) => string, href: (p: string) => string) {
  return breadcrumbJsonLd([
    { name: L("首頁", "Home"), path: href("/") },
    { name: L("新手入門", "Beginner guide"), path: href("/beginner") },
  ]);
}
