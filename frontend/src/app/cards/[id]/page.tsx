import type { Metadata } from "next";
import { CardDetailClient } from "@/components/CardDetailClient";
import { fetchCard } from "@/lib/api";
import { displayCardId } from "@/lib/cardId";
import {
  absoluteUrl,
  breadcrumbJsonLd,
  buildPageMetadata,
  cardJsonLd,
  cardOgImage,
  jsonLdScript,
} from "@/lib/seo";
import type { Card } from "@/lib/types";

function pickText(...values: Array<string | null | undefined>): string {
  for (const value of values) {
    const text = String(value || "").trim();
    if (text) return text;
  }
  return "";
}

function cardSeoFields(card: Card, fallbackId: string) {
  const id = displayCardId(card.id || fallbackId);
  const name = pickText(card.name, card.name_en, id);
  const nameEn = pickText(card.name_en);
  const rarity = pickText(card.rarity, "-");
  const series = pickText(card.pack_id, "-");
  const cardType = pickText(card.card_type, card.card_type_en, "-");
  const effect = pickText(card.effect, card.effect_en, "（暫無效果文本）");
  const trigger = pickText(card.trigger, card.trigger_en);
  const colors = (card.colors?.length ? card.colors : card.colors_en || []).join(" / ") || "-";
  return { id, name, nameEn, rarity, series, cardType, effect, trigger, colors };
}

async function loadCard(cardId: string): Promise<Card | null> {
  try {
    const data = await fetchCard(cardId, false);
    return data.card || null;
  } catch {
    return null;
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id: rawId } = await params;
  const cardId = decodeURIComponent(rawId);
  const path = `/cards/${encodeURIComponent(cardId)}`;
  const ogImage = cardOgImage(cardId);
  const card = await loadCard(cardId);

  if (!card) {
    return buildPageMetadata({
      title: `${displayCardId(cardId)} | OPCG 卡牌助手`,
      description: `查看 OPCG 卡牌 ${displayCardId(cardId)} 的資料、效果與市場價格。`,
      path,
      absoluteTitle: true,
      images: ogImage ? [ogImage] : undefined,
    });
  }

  const seo = cardSeoFields(card, cardId);
  const effectSnippet = seo.effect.replace(/\s+/g, " ").slice(0, 110);
  const description =
    `${seo.name}（${seo.id}）是《ONE PIECE 卡牌對戰》卡牌，系列 ${seo.series}，稀有度 ${seo.rarity}，類型 ${seo.cardType}。` +
    `效果：${effectSnippet}${seo.effect.length > 110 ? "…" : ""}`;

  return buildPageMetadata({
    title: `${seo.name}（${seo.id}）| OPCG 卡牌資料`,
    description,
    path,
    absoluteTitle: true,
    type: "article",
    keywords: [
      seo.name,
      seo.nameEn,
      seo.id,
      "OPCG",
      "ONE PIECE CARD GAME",
      seo.rarity,
      seo.series,
    ].filter(Boolean) as string[],
    images: ogImage ? [ogImage] : undefined,
  });
}

export default async function CardPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { id: rawId } = await params;
  const cardId = decodeURIComponent(rawId);
  const qp = await searchParams;
  const pickedRaw = qp.picked;
  const pickedVariantRaw = qp.pickedVariant;
  const picked = Array.isArray(pickedRaw) ? pickedRaw[0] : pickedRaw;
  const pickedVariant = Array.isArray(pickedVariantRaw) ? pickedVariantRaw[0] : pickedVariantRaw;
  const card = await loadCard(cardId);
  const seo = card ? cardSeoFields(card, cardId) : null;
  const ogImage = cardOgImage(cardId);

  const structured =
    seo &&
    [
      cardJsonLd({
        id: seo.id,
        name: seo.name,
        nameEn: seo.nameEn,
        description: seo.effect.replace(/\s+/g, " ").slice(0, 240),
        imageUrl: ogImage?.url,
        rarity: seo.rarity,
        series: seo.series,
      }),
      breadcrumbJsonLd([
        { name: "首頁", path: "/" },
        { name: "卡牌搜索", path: "/search" },
        { name: `${seo.name}（${seo.id}）`, path: `/cards/${encodeURIComponent(cardId)}` },
      ]),
    ];

  return (
    <div className="stack">
      {structured ? (
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: jsonLdScript(structured) }}
        />
      ) : null}
      {seo ? (
        <header className="card-seo-header seo-only" aria-hidden="true">
          <h1>
            {seo.name}
            {seo.nameEn && seo.nameEn !== seo.name ? ` / ${seo.nameEn}` : ""} {seo.id}
          </h1>
          <p>
            系列 {seo.series} · 稀有度 {seo.rarity} · 類型 {seo.cardType} · 顏色 {seo.colors}
            {card?.cost != null ? ` · 費用 ${card.cost}` : ""}
            {card?.power != null && card.power !== "" ? ` · 力量 ${card.power}` : ""}
          </p>
          <section>
            <h2>效果文本</h2>
            <p>{seo.effect}</p>
            {seo.trigger ? (
              <>
                <h2>觸發器</h2>
                <p>{seo.trigger}</p>
              </>
            ) : null}
            <p>完整卡牌頁面：{absoluteUrl(`/cards/${encodeURIComponent(cardId)}`)}</p>
          </section>
        </header>
      ) : null}
      <CardDetailClient
        cardId={cardId}
        picked={picked ? decodeURIComponent(picked) : undefined}
        pickedVariant={pickedVariant ? decodeURIComponent(pickedVariant) : undefined}
      />
    </div>
  );
}
