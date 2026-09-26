import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { cache } from "react";
import { CardDetailClient } from "@/components/CardDetailClient";
import { JsonLd } from "@/components/JsonLd";
import { ApiError, fetchCard, fetchCardTournaments, type CardTournamentAppearance } from "@/lib/api";
import { catalogHasCard, missingCardShould404 } from "@/lib/cardCatalog";
import { cardNotFoundMetadata } from "@/lib/cardNotFoundMetadata";
import { cardEditorNote } from "@/lib/cardEditorNotes";
import { displayCardId, setCodeFromCardId } from "@/lib/cardId";
import {
  breadcrumbJsonLd,
  buildPageMetadata,
  cardJsonLd,
  cardOgImage,
  faqPageJsonLd,
} from "@/lib/seo";
import type { Card } from "@/lib/types";

function pickText(...values: Array<string | null | undefined>): string {
  for (const value of values) {
    const text = String(value || "").trim();
    if (text) return text;
  }
  return "";
}

function firstSentence(text: string): string {
  const compact = text.replace(/\s+/g, " ").trim();
  const m = compact.match(/^.{8,160}?[。．.!?！？]/);
  return (m ? m[0] : compact).slice(0, 180);
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
  const traits = (card.traits?.length ? card.traits : card.traits_en || []).join(" / ");
  return { id, name, nameEn, rarity, series, cardType, effect, trigger, colors, traits };
}

const loadCard = cache(async (cardId: string): Promise<Card | null> => {
  try {
    const data = await fetchCard(cardId, false);
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
  const cardId = decodeURIComponent(rawId);
  const path = `/cards/${encodeURIComponent(cardId)}`;
  const ogImage = cardOgImage(cardId);
  const card = await loadCard(cardId);

  if (!card) return cardNotFoundMetadata;

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
  if (!card) notFound();
  const seo = card ? cardSeoFields(card, cardId) : null;
  const ogImage = cardOgImage(cardId);
  const editorNote = cardEditorNote(cardId);

  let appearances: CardTournamentAppearance[] = [];
  try {
    const tour = await fetchCardTournaments(cardId, 5);
    appearances = tour.items || [];
  } catch {
    appearances = [];
  }

  const faqItems: Array<{ question: string; answer: string }> = [];
  if (seo) {
    faqItems.push({
      question: `這張卡的卡號是什麼？`,
      answer: seo.id,
    });
    if (seo.effect && seo.effect !== "（暫無效果文本）") {
      faqItems.push({
        question: `${seo.name}（${seo.id}）的效果原文寫了什麼？`,
        answer: seo.effect.replace(/\s+/g, " ").trim().slice(0, 500),
      });
    }
    if (appearances.length) {
      const bits = appearances.slice(0, 3).map((row) => {
        const meta = row.meta_title || row.format || "賽事";
        const leader = row.leader_name || row.leader || "";
        return leader ? `${meta}（${leader}）` : meta;
      });
      faqItems.push({
        question: `${seo.name}（${seo.id}）常見於哪些賽事卡組？`,
        answer: `本站公開賽事資料中出現於：${bits.join("、")}。`,
      });
    }
  }

  const faqLd = faqPageJsonLd(faqItems);
  const structured = seo
    ? [
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
        ...(faqLd ? [faqLd] : []),
      ]
    : null;

  const summary = seo
    ? [
        `${seo.id} ${seo.name} 是${seo.colors !== "-" ? ` ${seo.colors} 色、` : ""}${card?.cost != null ? `費用 ${card.cost} 的` : ""}${seo.cardType}。`,
        card?.power != null && String(card.power) !== ""
          ? `力量 ${card.power}。效果：${firstSentence(seo.effect)}`
          : `效果：${firstSentence(seo.effect)}`,
      ].join(" ")
    : "";

  return (
    <div className="stack">
      <JsonLd data={structured} />
      {seo ? (
        <header className="card-seo-header seo-only" aria-hidden="true">
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
          <p className="card-seo-summary">{summary}</p>
          <dl className="card-seo-facts">
            {card?.cost != null ? (
              <>
                <dt>費用</dt>
                <dd>{card.cost}</dd>
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
            <dt>系列</dt>
            <dd>{seo.series}</dd>
            <dt>稀有度</dt>
            <dd>{seo.rarity}</dd>
          </dl>
          <section>
            <h2>效果文本</h2>
            <p>{seo.effect}</p>
            {seo.trigger ? (
              <>
                <h2>觸發器</h2>
                <p>{seo.trigger}</p>
              </>
            ) : null}
          </section>
          {editorNote ? (
            <section>
              <h2>編輯說明</h2>
              <p>{editorNote}</p>
            </section>
          ) : null}
          {faqItems.length ? (
            <section>
              <h2>常見問題</h2>
              {faqItems.map((item) => (
                <div key={item.question}>
                  <h3>{item.question}</h3>
                  <p>{item.answer}</p>
                </div>
              ))}
            </section>
          ) : null}
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
