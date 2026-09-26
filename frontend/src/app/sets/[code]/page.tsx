import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { displayCardId } from "@/lib/cardId";
import {
  SITE_URL,
  breadcrumbJsonLd,
  buildPageMetadata,
  jsonLdScript,
} from "@/lib/seo";
import { allSets, getSet, setLabel, setPageDescription, setPageTitle } from "@/lib/sets";

export function generateStaticParams() {
  return allSets().map((s) => ({ code: s.code }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ code: string }>;
}): Promise<Metadata> {
  const { code: raw } = await params;
  const code = decodeURIComponent(raw).toUpperCase();
  const set = getSet(code);
  if (!set) {
    return buildPageMetadata({
      title: `${code} 卡表｜OPCG 卡牌助手`,
      description: `查詢 OPCG 系列 ${code} 的卡牌列表。`,
      path: `/sets/${encodeURIComponent(code)}`,
      absoluteTitle: true,
    });
  }
  return buildPageMetadata({
    title: setPageTitle(code),
    description: setPageDescription(code, set.count),
    path: `/sets/${encodeURIComponent(code)}`,
    absoluteTitle: true,
    keywords: [code, setLabel(code), `${code} 卡表`, `${setLabel(code)} 卡表`, "OPCG", "ONE PIECE CARD GAME"],
  });
}

export default async function SetPage({ params }: { params: Promise<{ code: string }> }) {
  const { code: raw } = await params;
  const code = decodeURIComponent(raw).toUpperCase();
  const set = getSet(code);
  if (!set) notFound();
  const label = setLabel(code);
  const collectionLd = {
    "@context": "https://schema.org",
    "@type": "CollectionPage",
    name: setPageTitle(code),
    url: `${SITE_URL}/sets/${encodeURIComponent(code)}`,
    description: setPageDescription(code, set.count),
    isPartOf: { "@type": "WebSite", name: "OPCG 卡牌助手", url: SITE_URL },
    mainEntity: {
      "@type": "ItemList",
      numberOfItems: set.count,
      itemListElement: set.cards.slice(0, 80).map((c, i) => ({
        "@type": "ListItem",
        position: i + 1,
        name: `${c.name}（${displayCardId(c.id)}）`,
        url: `${SITE_URL}/cards/${encodeURIComponent(c.id)}`,
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
              { name: "首頁", path: "/" },
              { name: "系列卡表", path: "/sets" },
              { name: label, path: `/sets/${encodeURIComponent(code)}` },
            ]),
          ),
        }}
      />
      <nav className="set-page-nav muted">
        <Link href="/sets">系列卡表</Link>
        {" / "}
        <span>{label}</span>
      </nav>
      <h1 className="page-title">
        {label} 卡表
        <span className="muted"> · {set.count} 張</span>
      </h1>
      <p>
        《ONE PIECE 卡牌對戰》{label}（{code}）全卡列表。點卡號可看效果、異畫、市場價格，並加入卡組或對戰練習。
      </p>
      <ul className="set-card-list">
        {set.cards.map((c) => (
          <li key={c.id}>
            <Link href={`/cards/${encodeURIComponent(c.id)}`}>
              <span className="set-card-id">{displayCardId(c.id)}</span>
              <span>{c.name}</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
