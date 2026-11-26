import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { displayCardId } from "@/lib/cardId";
import { localizeCardName } from "@/lib/cardLocale";
import {
  SITE_URL,
  breadcrumbJsonLd,
  buildPageMetadata,
  jsonLdScript,
} from "@/lib/seo";
import { serverCopy, type ServerCopy } from "@/lib/serverCopy";
import {
  getSet,
  setLabel,
  setLabelEn,
  setPageDescription,
  setPageDescriptionEn,
  setPageTitle,
  setPageTitleEn,
  type SetCardRow,
} from "@/lib/sets";

function titleFor(copy: ServerCopy, code: string): string {
  return copy.L(setPageTitle(code), setPageTitleEn(code));
}

function descriptionFor(copy: ServerCopy, code: string, count: number): string {
  return copy.L(setPageDescription(code, count), setPageDescriptionEn(code, count));
}

function cardName(copy: ServerCopy, c: SetCardRow): string {
  if (copy.lang === "en") return c.en || c.name;
  if (copy.lang === "zh-Hans") return copy.hans(localizeCardName(c.name, c.en, "zh-Hans") || c.name);
  return c.name;
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ code: string }>;
}): Promise<Metadata> {
  const { code: raw } = await params;
  const code = decodeURIComponent(raw).toUpperCase();
  const copy = await serverCopy();
  const set = getSet(code);
  if (!set) {
    return buildPageMetadata({
      title: copy.L(`${code} 卡表｜OPCG 卡牌助手`, `${code} Card List | OPCG Card Assistant`),
      description: copy.L(`查詢 OPCG 系列 ${code} 的卡牌列表。`, `ONE PIECE CARD GAME ${code} card list.`),
      path: `/sets/${encodeURIComponent(code)}`,
      absoluteTitle: true,
      lang: copy.lang,
    });
  }
  const label = copy.lang === "en" ? setLabelEn(code) : setLabel(code);
  return buildPageMetadata({
    title: titleFor(copy, code),
    description: descriptionFor(copy, code, set.count),
    path: `/sets/${encodeURIComponent(code)}`,
    absoluteTitle: true,
    lang: copy.lang,
    keywords: [
      code,
      label,
      copy.L(`${code} 卡表`, `${code} card list`),
      copy.L(`${setLabel(code)} 卡表`, `${label} cards`),
      "OPCG",
      "ONE PIECE CARD GAME",
    ],
  });
}

export default async function SetPage({ params }: { params: Promise<{ code: string }> }) {
  const { code: raw } = await params;
  const code = decodeURIComponent(raw).toUpperCase();
  const set = getSet(code);
  if (!set) notFound();
  const copy = await serverCopy();
  const { L, href } = copy;
  const label = copy.lang === "en" ? setLabelEn(code) : setLabel(code);
  const unconfirmedCount = set.cards.filter((c) => c.unconfirmed).length;
  const pageUrl = `${SITE_URL}${href(`/sets/${encodeURIComponent(code)}`)}`;
  const collectionLd = {
    "@context": "https://schema.org",
    "@type": "CollectionPage",
    name: titleFor(copy, code),
    url: pageUrl,
    description: descriptionFor(copy, code, set.count),
    inLanguage: copy.lang,
    isPartOf: { "@type": "WebSite", name: L("OPCG 卡牌助手", "OPCG Card Assistant"), url: SITE_URL },
    mainEntity: {
      "@type": "ItemList",
      numberOfItems: set.count,
      itemListElement: set.cards.slice(0, 80).map((c, i) => ({
        "@type": "ListItem",
        position: i + 1,
        name: L(`${cardName(copy, c)}（${displayCardId(c.id)}）`, `${cardName(copy, c)} (${displayCardId(c.id)})`),
        url: `${SITE_URL}${href(`/cards/${encodeURIComponent(c.id)}`)}`,
      })),
    },
  };

  return (
    <div className="stack set-page">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLdScript(collectionLd) }} />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: jsonLdScript(
            breadcrumbJsonLd([
              { name: L("首頁", "Home"), path: href("/") },
              { name: L("系列卡表", "Set lists"), path: href("/sets") },
              { name: label, path: href(`/sets/${encodeURIComponent(code)}`) },
            ]),
          ),
        }}
      />
      <nav className="set-page-nav muted">
        <Link href={href("/sets")}>{L("系列卡表", "Set lists")}</Link>
        {" / "}
        <span>{label}</span>
      </nav>
      <h1 className="page-title">
        {L(`${label} 卡表`, `${label} card list`)}
        <span className="muted">{L(` · ${set.count} 張`, ` · ${set.count} cards`)}</span>
      </h1>
      <p>
        {L(
          `《ONE PIECE 卡牌對戰》${label}（${code}）全卡列表。點卡號可看效果、異畫、市場價格，並加入卡組或對戰練習。`,
          `Every ONE PIECE CARD GAME card in ${label} (${code}). Open a card for its effect, parallel arts and market price, or add it to a deck.`,
        )}
      </p>
      {unconfirmedCount ? (
        <p className="set-unconfirmed-note" role="note">
          <span className="set-card-unconfirmed">{L("未確認 Unconfirmed", "Unconfirmed")}</span>{" "}
          {L(
            `官方卡表尚未公開本系列。標示「未確認」的 ${unconfirmedCount} 張取自官方直播公開畫面與第三方發售前卡表，中文為本站暫譯，卡圖為暫用圖，官方公開後會更新。`,
            `This set is not on the official card list yet. The ${unconfirmedCount} cards marked "Unconfirmed" come from official stream reveals and pre-release lists; text and images are provisional and will be updated.`,
          )}
          {copy.lang === "en" ? null : " Not on the official card list yet; these cards may change."}
        </p>
      ) : null}
      <ul className="set-card-list">
        {set.cards.map((c) => (
          <li key={c.id}>
            <Link href={href(`/cards/${encodeURIComponent(c.id)}`)}>
              <span className="set-card-id">{displayCardId(c.id)}</span>
              <span>{cardName(copy, c)}</span>
              {c.unconfirmed ? <span className="set-card-unconfirmed">{L("未確認", "Unconfirmed")}</span> : null}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
