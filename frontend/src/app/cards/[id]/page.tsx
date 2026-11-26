import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { cache } from "react";
import { preload } from "react-dom";
import { CardDetailClient } from "@/components/CardDetailClient";
import { JsonLd } from "@/components/JsonLd";
import { stripAbsentCardImageUrls, type CardTournamentAppearance } from "@/lib/api";
import { heroPreloadHref } from "@/lib/cardImageSrcSet";
import { catalogCard, catalogHasCard, normalizeCatalogCardId } from "@/lib/cardCatalog";
import { cardUnavailableMetadata, resolveCardPageLoad, type CardPageLoad } from "@/lib/cardPageFallback";
import { getCachedCardDetail, getCachedCardTournaments } from "@/lib/cardPageData";
import { markCardPageUnavailable } from "@/lib/cardPageStatus";
import { cardNotFoundMetadata } from "@/lib/cardNotFoundMetadata";
import { tournamentFaqAnswer } from "@/lib/cardTournamentFaq";
import { cardEditorNote } from "@/lib/cardEditorNotes";
import { cardDocumentTitle, isLeaderCardType, printedCostOrLife, shownCardId } from "@/lib/cardPageView";
import { displayCardId, isDonCardId, normalizeCardId, setCodeFromCardId, toBaseCardId } from "@/lib/cardId";
import {
  CARD_PAGE_ORIGIN,
  cardCanonicalUrl,
  cardMetaDescription,
  presentMetaText,
} from "@/lib/parallelArts";
import {
  breadcrumbJsonLd,
  buildPageMetadata,
  cardJsonLd,
  cardSharePresentation,
  faqPageJsonLd,
  visibleCardEffect,
} from "@/lib/seo";
import type { Card } from "@/lib/types";
import { serverCopy, type ServerCopy } from "@/lib/serverCopy";
import { localizeCardName } from "@/lib/cardLocale";

function pickText(...values: Array<string | null | undefined>): string {
  for (const value of values) {
    const text = String(value || "").trim();
    if (text) return text;
  }
  return "";
}

function cardSeoFields(card: Card, fallbackId: string, copy?: ServerCopy) {
  const id = displayCardId(card.id || fallbackId);
  const lang = copy?.lang ?? "zh-Hant";
  const nameEn = pickText(card.name_en);
  const rarity = pickText(card.rarity, "-");
  const series = setCodeFromCardId(id) || "-";
  if (lang === "en") {
    const name = presentMetaText(pickText(card.name_en, card.name)) || id;
    const cardType = pickText(card.card_type_en, card.card_type, "-");
    const effect = visibleCardEffect(pickText(card.effect_en, card.effect));
    const colors = (card.colors_en?.length ? card.colors_en : card.colors || []).join(" / ") || "-";
    const traits = (card.traits_en?.length ? card.traits_en : card.traits || []).join(" / ");
    return { id, name, nameEn, rarity, series, cardType, effect, colors, traits };
  }
  const h = copy?.hans ?? ((text: string) => text);
  const baseName = presentMetaText(pickText(card.name, card.name_en)) || id;
  const name =
    lang === "zh-Hans" ? h(localizeCardName(card.name, card.name_en, "zh-Hans") || baseName) : baseName;
  const cardType = h(pickText(card.card_type, card.card_type_en, "-"));
  const effect = h(visibleCardEffect(pickText(card.effect, card.effect_en)));
  const colors = h((card.colors?.length ? card.colors : card.colors_en || []).join(" / ") || "-");
  const traits = h((card.traits?.length ? card.traits : card.traits_en || []).join(" / "));
  return { id, name, nameEn, rarity, series, cardType, effect, colors, traits };
}

function cardDescriptionFor(copy: ServerCopy, seo: ReturnType<typeof cardSeoFields>): string {
  if (copy.lang !== "en") {
    return copy.hans(
      cardMetaDescription({
        name: seo.name,
        id: seo.id,
        series: seo.series,
        rarity: seo.rarity,
        cardType: seo.cardType,
        effect: seo.effect,
      }),
    );
  }
  const parts = [
    presentMetaText(seo.series) ? `set ${seo.series}` : "",
    presentMetaText(seo.rarity) ? `rarity ${seo.rarity}` : "",
    presentMetaText(seo.cardType) ? `type ${seo.cardType}` : "",
  ].filter(Boolean);
  const effect = presentMetaText(seo.effect).replace(/\s+/g, " ");
  const snippet = effect.slice(0, 140);
  return `${seo.name} (${seo.id}) is a ONE PIECE CARD GAME card${parts.length ? `: ${parts.join(", ")}` : ""}.${
    effect ? ` Effect: ${snippet}${effect.length > 140 ? "…" : ""}` : ""
  }`;
}

const lastSuccessfulCards = new Map<string, Card>();

/**
 * One API read per id (React cache plus the 5s no-retry fetch). A short outage
 * reuses the last success or the bundled index row. No data becomes a retry
 * state, not a thrown 500 and not a 404 for an id that may exist.
 */
const loadCard = cache(async (cardId: string): Promise<CardPageLoad> => {
  return resolveCardPageLoad(cardId, () => getCachedCardDetail(cardId), {
    knownInCatalog: () => catalogHasCard(cardId),
    readStatic: (id) => catalogCard(id),
    memory: lastSuccessfulCards,
  });
});

function cardRetryPath(cardId: string, picked: string, pickedVariant: string): string {
  const params = new URLSearchParams();
  if (picked) params.set("picked", picked);
  if (pickedVariant) params.set("pickedVariant", pickedVariant);
  const query = params.toString();
  return `/cards/${encodeURIComponent(cardId)}${query ? `?${query}` : ""}`;
}

function CardRetryState({ cardId, picked, pickedVariant, retryAfterSeconds }: {
  cardId: string;
  picked: string;
  pickedVariant: string;
  retryAfterSeconds: number;
}) {
  return (
    <div className="stack" role="status">
      <h1 className="page-title">卡牌暫時無法載入</h1>
      <p className="muted">
        資料服務暫時沒有回應。請約 {retryAfterSeconds} 秒後再試，這個頁面會重新讀取卡牌。
      </p>
      <p className="legal-links">
        <a href={cardRetryPath(cardId, picked, pickedVariant)}>重試</a>
        {" · "}
        <Link href="/search">前往卡牌搜索</Link>
      </p>
    </div>
  );
}

function firstQueryValue(value: string | string[] | undefined): string {
  const raw = Array.isArray(value) ? value[0] : value;
  if (!raw) return "";
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}

export async function generateMetadata({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<Metadata> {
  const { id: rawId } = await params;
  const cardId = normalizeCardId(decodeURIComponent(rawId));
  const qp = await searchParams;
  const shownId = shownCardId(cardId, firstQueryValue(qp.picked), firstQueryValue(qp.pickedVariant));
  const canonicalUrl = cardCanonicalUrl(cardId);
  const loaded = await loadCard(cardId);
  if (loaded.kind === "unavailable") return cardUnavailableMetadata;
  if (loaded.kind === "missing") return cardNotFoundMetadata;
  const card = loaded.card;
  const share = cardSharePresentation(card);
  const copy = await serverCopy();

  const seo = cardSeoFields(card, cardId, copy);
  const description = cardDescriptionFor(copy, seo);

  return buildPageMetadata({
    title: cardDocumentTitle(seo.name, shownId, copy.lang),
    description,
    path: canonicalUrl,
    absoluteTitle: true,
    lang: copy.lang,
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
    images: share.images,
    twitterCard: share.twitterCard,
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
  const picked = firstQueryValue(qp.picked);
  const pickedVariant = firstQueryValue(qp.pickedVariant);
  // Hash comes from the build manifest, so this can run before the card fetch.
  // A preload registered after that await is too late for the document head.
  const heroId = shownCardId(cardId, picked, pickedVariant);
  const heroSrc = heroPreloadHref(heroId);
  if (heroSrc && !/localhost|127\.0\.0\.1/i.test(heroSrc)) {
    preload(heroSrc, { as: "image", fetchPriority: "high" });
  }
  const loaded = await loadCard(cardId);
  if (loaded.kind === "missing") notFound();
  if (loaded.kind === "unavailable") {
    markCardPageUnavailable(loaded.retryAfterSeconds);
    return (
      <CardRetryState
        cardId={cardId}
        picked={picked}
        pickedVariant={pickedVariant}
        retryAfterSeconds={loaded.retryAfterSeconds}
      />
    );
  }
  const card = loaded.card;
  // Same payload the client uses: non-DON pages load the base card so every
  // alternate-art thumbnail is present. The URL card still supplies the price
  // of the printing this page opened on. A fallback already means the API
  // missed, so the base card is read locally instead of starting another call.
  const baseId = toBaseCardId(cardId);
  let detailCard = card;
  if (!isDonCardId(cardId) && baseId !== normalizeCardId(cardId)) {
    if (loaded.source === "api") {
      try {
        const baseLoaded = await loadCard(baseId);
        if (baseLoaded.kind === "card") detailCard = baseLoaded.card;
      } catch {
        detailCard = card;
      }
    } else {
      const baseCard = lastSuccessfulCards.get(normalizeCatalogCardId(baseId)) || catalogCard(baseId);
      if (baseCard) detailCard = baseCard;
    }
  }
  const copy = await serverCopy();
  const { L, href } = copy;
  const seo = card ? cardSeoFields(card, cardId, copy) : null;
  const share = cardSharePresentation(card);
  const editorNote = cardEditorNote(cardId);
  const printedStat = printedCostOrLife(card);

  let appearances: CardTournamentAppearance[] = [];
  let initialTournaments: { items: CardTournamentAppearance[]; total: number } | undefined;
  // The card fetch already failed over. Another tournament request would only
  // wait out the same outage; the section is omitted until the API answers.
  if (loaded.source === "api") {
    try {
      const tour = await getCachedCardTournaments(cardId, 10);
      appearances = tour.items || [];
      initialTournaments = { items: appearances, total: tour.total_matched || 0 };
    } catch {
      appearances = [];
    }
  }

  const faqItems: Array<{ question: string; answer: string }> = [];
  if (seo) {
    faqItems.push({
      question: L(`這張卡的卡號是什麼？`, "What is this card's number?"),
      answer: seo.id,
    });
    if (seo.effect) {
      faqItems.push({
        question: L(`${seo.name}（${seo.id}）的效果原文寫了什麼？`, `What does ${seo.name} (${seo.id}) do?`),
        answer: seo.effect,
      });
    }
    if (appearances.length && copy.lang !== "en") {
      faqItems.push({
        question: L(`${seo.name}（${seo.id}）常見於哪些賽事卡組？`, ""),
        answer: L(tournamentFaqAnswer(appearances), ""),
      });
    }
  }

  const faqLd = faqPageJsonLd(faqItems);
  const canonicalUrl = `${CARD_PAGE_ORIGIN}${href(new URL(cardCanonicalUrl(cardId)).pathname)}`;
  const structured = seo
    ? [
        cardJsonLd({
          id: seo.id,
          name: seo.name,
          nameEn: seo.nameEn,
          description: (seo.effect || seo.name).replace(/\s+/g, " ").slice(0, 240),
          imageUrl: share.jsonLdImage,
          rarity: presentMetaText(seo.rarity) || undefined,
          series: presentMetaText(seo.series) || undefined,
          url: canonicalUrl,
        }),
        breadcrumbJsonLd([
          { name: L("首頁", "Home"), path: href("/") },
          { name: L("卡牌搜索", "Card search"), path: href("/search") },
          { name: L(`${seo.name}（${seo.id}）`, `${seo.name} (${seo.id})`), path: canonicalUrl },
        ]),
        ...(faqLd ? [faqLd] : []),
      ]
    : null;

  const summary = seo
    ? copy.lang === "en"
      ? [
          `${seo.id} ${seo.name} is a${seo.colors !== "-" ? ` ${seo.colors}` : ""} ${seo.cardType}${
            printedStat ? ` with ${printedStat.kind === "life" ? "life" : "cost"} ${printedStat.value}` : ""
          }.`,
          card?.power != null && String(card.power) !== "" ? `Power ${card.power}.` : "",
        ]
          .filter(Boolean)
          .join(" ")
      : copy.hans(
          [
            `${seo.id} ${seo.name} 是${seo.colors !== "-" ? ` ${seo.colors} 色、` : ""}${printedStat ? `${printedStat.kind === "life" ? "生命" : "費用"} ${printedStat.value} 的` : ""}${seo.cardType}。`,
            card?.power != null && String(card.power) !== "" ? `力量 ${card.power}。` : "",
          ]
            .filter(Boolean)
            .join(" "),
        )
    : "";

  const cardSupplement = seo ? (
    <section className="card-seo-more">
      <p className="card-seo-summary">{summary}</p>
      <dl className="card-seo-facts">
        {printedStat ? (
          <>
            <dt>{printedStat.kind === "life" ? L("生命", "Life") : L("費用", "Cost")}</dt>
            <dd>{printedStat.value}</dd>
          </>
        ) : null}
        {card?.power != null && String(card.power) !== "" ? (
          <>
            <dt>{L("力量", "Power")}</dt>
            <dd>{card.power}</dd>
          </>
        ) : null}
        {card?.counter != null && String(card.counter) !== "" ? (
          <>
            <dt>{L("反擊", "Counter")}</dt>
            <dd>{card.counter}</dd>
          </>
        ) : null}
        {seo.colors !== "-" ? (
          <>
            <dt>{L("顏色", "Color")}</dt>
            <dd>{seo.colors}</dd>
          </>
        ) : null}
        {seo.traits ? (
          <>
            <dt>{L("特徵", "Traits")}</dt>
            <dd>{seo.traits}</dd>
          </>
        ) : null}
        {seo.series !== "-" ? (
          <>
            <dt>{L("系列", "Set")}</dt>
            <dd>{seo.series}</dd>
          </>
        ) : null}
        <dt>{L("稀有度", "Rarity")}</dt>
        <dd>{seo.rarity}</dd>
      </dl>
      {isLeaderCardType(card.card_type_en || card.card_type) && appearances.length ? (
        <p>
          <Link href={href(`/leaders/${encodeURIComponent(toBaseCardId(cardId))}`)}>
            {L("這個領袖的賽事統計：上榜次數、冠軍卡組與常用卡 →", "Leader stats: tournament decks, champion lists and common cards →")}
          </Link>
        </p>
      ) : null}
      {editorNote && copy.lang !== "en" ? (
        <section>
          <h2>{L("編輯說明", "Editor note")}</h2>
          <p>{copy.lang === "zh-Hans" ? copy.hans(editorNote) : editorNote}</p>
        </section>
      ) : null}
      {faqItems.length ? (
        <details className="card-seo-faq">
          <summary>
            <h2>{L("常見問題", "FAQ")}</h2>
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
        picked={picked || undefined}
        pickedVariant={pickedVariant || undefined}
        afterDetails={cardSupplement}
        initialCard={stripAbsentCardImageUrls(detailCard)}
        initialMarketPrice={card.market_price ?? null}
        initialPriceCardId={cardId}
        initialTournaments={initialTournaments}
      />
    </div>
  );
}
