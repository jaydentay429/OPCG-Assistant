import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { cache } from "react";
import { CardDetailClient } from "@/components/CardDetailClient";
import { JsonLd } from "@/components/JsonLd";
import { ApiError, type CardTournamentAppearance } from "@/lib/api";
import { getCachedCardDetail, getCachedCardTournaments } from "@/lib/cardPageData";
import { catalogHasCard, missingCardShould404 } from "@/lib/cardCatalog";
import { cardNotFoundMetadata } from "@/lib/cardNotFoundMetadata";
import { tournamentFaqAnswer } from "@/lib/cardTournamentFaq";
import { cardEditorNote } from "@/lib/cardEditorNotes";
import { printedCostOrLife } from "@/lib/cardPageView";
import { displayCardId, isDonCardId, normalizeCardId, setCodeFromCardId, toBaseCardId } from "@/lib/cardId";
import {
  cardCanonicalUrl,
  cardMetaDescription,
  presentMetaText,
} from "@/lib/parallelArts";
import {
  breadcrumbJsonLd,
  buildPageMetadata,
  cardJsonLd,
  cardOgImage,
  faqPageJsonLd,
  visibleCardEffect,
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
  const name = presentMetaText(pickText(card.name, card.name_en)) || id;
  const nameEn = pickText(card.name_en);
  const rarity = pickText(card.rarity, "-");
  const series = setCodeFromCardId(id) || "-";
  const cardType = pickText(card.card_type, card.card_type_en, "-");
  const effect = visibleCardEffect(pickText(card.effect, card.effect_en));
  const colors = (card.colors?.length ? card.colors : card.colors_en || []).join(" / ") || "-";
  const traits = (card.traits?.length ? card.traits : card.traits_en || []).join(" / ");
  return { id, name, nameEn, rarity, series, cardType, effect, colors, traits };
}

const loadCard = cache(async (cardId: string): Promise<Card | null> => {
  try {
    const data = await getCachedCardDetail(cardId);
    if (data.card) return data.card;
    if (!missingCardShould404(null, catalogHasCard(cardId))) {
      throw new Error(`Card API returned no card for catalogued id ${cardId}`);
    }
    return null;
  } catch (error) {
    // Only 404/422 can be a real miss. 5xx and timeouts must throw so they are
    // not published as a not-found page for an id that may still exist.
    if (
      error instanceof ApiError &&
      (error.status === 404 || error.status === 422) &&
      missingCardShould404(error.status, catalogHasCard(cardId))
    ) {
      return null;
    }
    throw error;
  }
});

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id: rawId } = await params;
  const cardId = normalizeCardId(decodeURIComponent(rawId));
  const canonicalUrl = cardCanonicalUrl(cardId);
  const ogImage = cardOgImage(cardId);
  const card = await loadCard(cardId);

  if (!card) return cardNotFoundMetadata;

  const seo = cardSeoFields(card, cardId);
  const description = cardMetaDescription({
    name: seo.name,
    id: seo.id,
    series: seo.series,
    rarity: seo.rarity,
    cardType: seo.cardType,
    effect: seo.effect,
  });

  return buildPageMetadata({
    title: `${seo.name}（${seo.id}）| OPCG 卡牌資料`,
    description,
    path: canonicalUrl,
    absoluteTitle: true,
    type: "article",
    keywords: [
      seo.name,
      seo.nameEn,
      seo.id,
      "OPCG",
      "ONE PIECE CARD GAME",
      presentMetaText(seo.rarity),
      presentMetaText(seo.series),
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
  const cardId = normalizeCardId(decodeURIComponent(rawId));
  const qp = await searchParams;
  const pickedRaw = qp.picked;
  const pickedVariantRaw = qp.pickedVariant;
  const picked = Array.isArray(pickedRaw) ? pickedRaw[0] : pickedRaw;
  const pickedVariant = Array.isArray(pickedVariantRaw) ? pickedVariantRaw[0] : pickedVariantRaw;
  const card = await loadCard(cardId);
  if (!card) notFound();
  // Same payload the client uses: non-DON pages load the base card so every
  // alternate-art thumbnail is present. The URL card still supplies the price
  // of the printing this page opened on.
  const baseId = toBaseCardId(cardId);
  let detailCard = card;
  if (!isDonCardId(cardId) && baseId !== normalizeCardId(cardId)) {
    try {
      const baseCard = await loadCard(baseId);
      if (baseCard) detailCard = baseCard;
    } catch {
      detailCard = card;
    }
  }
  const seo = card ? cardSeoFields(card, cardId) : null;
  const ogImage = cardOgImage(cardId);
  const editorNote = cardEditorNote(cardId);
  const printedStat = printedCostOrLife(card);

  let appearances: CardTournamentAppearance[] = [];
  let initialTournaments: { items: CardTournamentAppearance[]; total: number } | undefined;
  try {
    const tour = await getCachedCardTournaments(cardId, 10);
    appearances = tour.items || [];
    initialTournaments = { items: appearances, total: tour.total_matched || 0 };
  } catch {
    appearances = [];
  }

  const faqItems: Array<{ question: string; answer: string }> = [];
  if (seo) {
    faqItems.push({
      question: `這張卡的卡號是什麼？`,
      answer: seo.id,
    });
    if (seo.effect) {
      faqItems.push({
        question: `${seo.name}（${seo.id}）的效果原文寫了什麼？`,
        answer: seo.effect,
      });
    }
    if (appearances.length) {
      faqItems.push({
        question: `${seo.name}（${seo.id}）常見於哪些賽事卡組？`,
        answer: tournamentFaqAnswer(appearances),
      });
    }
  }

  const faqLd = faqPageJsonLd(faqItems);
  const canonicalUrl = cardCanonicalUrl(cardId);
  const structured = seo
    ? [
        cardJsonLd({
          id: seo.id,
          name: seo.name,
          nameEn: seo.nameEn,
          description: (seo.effect || seo.name).replace(/\s+/g, " ").slice(0, 240),
          imageUrl: ogImage?.url,
          rarity: presentMetaText(seo.rarity) || undefined,
          series: presentMetaText(seo.series) || undefined,
          url: canonicalUrl,
        }),
        breadcrumbJsonLd([
          { name: "首頁", path: "/" },
          { name: "卡牌搜索", path: "/search" },
          { name: `${seo.name}（${seo.id}）`, path: canonicalUrl },
        ]),
        ...(faqLd ? [faqLd] : []),
      ]
    : null;

  const summary = seo
    ? [
        `${seo.id} ${seo.name} 是${seo.colors !== "-" ? ` ${seo.colors} 色、` : ""}${printedStat ? `${printedStat.kind === "life" ? "生命" : "費用"} ${printedStat.value} 的` : ""}${seo.cardType}。`,
        card?.power != null && String(card.power) !== "" ? `力量 ${card.power}。` : "",
      ]
        .filter(Boolean)
        .join(" ")
    : "";

  const cardTitle = seo ? (
    <div className="card-page-heading">
      <nav className="set-page-nav muted">
        <Link href="/">首頁</Link>
        {" / "}
        <Link href="/search">卡牌搜索</Link>
        {setCodeFromCardId(seo.id) ? (
          <>
            {" / "}
            <Link href={`/sets/${encodeURIComponent(setCodeFromCardId(seo.id) || "")}`}>
              {setCodeFromCardId(seo.id)}
            </Link>
          </>
        ) : null}
      </nav>
      <h1>
        {seo.name}
        {seo.nameEn && seo.nameEn !== seo.name ? ` / ${seo.nameEn}` : ""} {seo.id}
      </h1>
    </div>
  ) : null;

  const cardSupplement = seo ? (
    <section className="card-seo-more">
      <p className="card-seo-summary">{summary}</p>
      <dl className="card-seo-facts">
        {printedStat ? (
          <>
            <dt>{printedStat.kind === "life" ? "生命" : "費用"}</dt>
            <dd>{printedStat.value}</dd>
          </>
        ) : null}
        {card?.power != null && String(card.power) !== "" ? (
          <>
            <dt>力量</dt>
            <dd>{card.power}</dd>
          </>
        ) : null}
        {card?.counter != null && String(card.counter) !== "" ? (
          <>
            <dt>反擊</dt>
            <dd>{card.counter}</dd>
          </>
        ) : null}
        {seo.colors !== "-" ? (
          <>
            <dt>顏色</dt>
            <dd>{seo.colors}</dd>
          </>
        ) : null}
        {seo.traits ? (
          <>
            <dt>特徵</dt>
            <dd>{seo.traits}</dd>
          </>
        ) : null}
        {seo.series !== "-" ? (
          <>
            <dt>系列</dt>
            <dd>{seo.series}</dd>
          </>
        ) : null}
        <dt>稀有度</dt>
        <dd>{seo.rarity}</dd>
      </dl>
      {editorNote ? (
        <section>
          <h2>編輯說明</h2>
          <p>{editorNote}</p>
        </section>
      ) : null}
      {faqItems.length ? (
        <details className="card-seo-faq">
          <summary>
            <h2>常見問題</h2>
          </summary>
          {faqItems.map((item) => (
            <div key={item.question}>
              <h3>{item.question}</h3>
              <p>{item.answer}</p>
            </div>
          ))}
        </details>
      ) : null}
    </section>
  ) : null;

  return (
    <div className="stack">
      <JsonLd data={structured} allowFaq={faqItems.length > 0} />
      <CardDetailClient
        key={cardId}
        cardId={cardId}
        picked={picked ? decodeURIComponent(picked) : undefined}
        pickedVariant={pickedVariant ? decodeURIComponent(pickedVariant) : undefined}
        cardTitle={cardTitle}
        afterDetails={cardSupplement}
        initialCard={detailCard}
        initialMarketPrice={card.market_price ?? null}
        initialPriceCardId={cardId}
        initialTournaments={initialTournaments}
      />
    </div>
  );
}
