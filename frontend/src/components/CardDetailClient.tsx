"use client";

import { useEffect, useLayoutEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { collectionAdd, collectionRemove, fetchCard, fetchCardPrice, fetchCollection } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useDeck } from "@/lib/deck";
import { useI18n } from "@/lib/i18n";
import { displayCardId, isDonCardId, normalizeCardId, toBaseCardId } from "@/lib/cardId";
import { localizeCardList, localizeCardName, localizeCardSources, localizeCardText, localizeDonCardName, preferLangText } from "@/lib/cardLocale";
import { localizeFilterToken, localizeFilterTokens } from "@/lib/filterLabels";
import { formatEffectLines } from "@/lib/formatEffect";
import type { Card, CardPriceResponse, PriceHistoryPoint } from "@/lib/types";
import {
  clearCardDetailScroll,
  readPathScrollTarget,
  requestScrollRestore,
} from "@/lib/scrollRestore";
import { CardImg } from "./CardImg";
import { CardDetailExtras } from "./CardDetailExtras";

type VariantMeta = {
  baseId: string;
  variantId: string;
  /** sort: base=0, then letter rank, then number */
  sortKey: string;
};

function formatYen(value: number): string {
  return `¥${Math.round(value).toLocaleString("ja-JP")}`;
}

function PriceChart({ history, lang }: { history: PriceHistoryPoint[]; lang: string }) {
  const points = history
    .map((row) => ({ ts: new Date(row.ts), price: Number(row.price) }))
    .filter((row) => Number.isFinite(row.ts.getTime()) && Number.isFinite(row.price) && row.price >= 0)
    .sort((a, b) => a.ts.getTime() - b.ts.getTime());
  if (points.length === 0) return null;

  const width = 720;
  const height = 260;
  const margin = { top: 18, right: 20, bottom: 48, left: 76 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const minPrice = Math.min(...points.map((point) => point.price));
  const maxPrice = Math.max(...points.map((point) => point.price));
  const padding = Math.max((maxPrice - minPrice) * 0.12, maxPrice * 0.05, 1);
  const yMin = Math.max(0, minPrice - padding);
  const yMax = maxPrice + padding;
  const xFor = (index: number) =>
    margin.left + (points.length === 1 ? plotWidth / 2 : (index / (points.length - 1)) * plotWidth);
  const yFor = (price: number) =>
    margin.top + plotHeight - ((price - yMin) / Math.max(1, yMax - yMin)) * plotHeight;
  const line = points.map((point, index) => `${xFor(index)},${yFor(point.price)}`).join(" ");
  const locale = lang === "en" ? "en-US" : lang === "zh-Hant" ? "zh-HK" : "zh-CN";
  const dateText = (date: Date) =>
    new Intl.DateTimeFormat(locale, { year: "2-digit", month: "2-digit", day: "2-digit" }).format(date);
  const yTicks = Array.from({ length: 5 }, (_, index) => yMin + ((yMax - yMin) * index) / 4);
  const xTickIndexes = Array.from(
    new Set([0, Math.floor((points.length - 1) / 2), points.length - 1]),
  );

  return (
    <div className="price-chart-scroll">
      <svg
        className="price-chart"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Card price history"
      >
        {yTicks.map((value) => {
          const y = yFor(value);
          return (
            <g key={value}>
              <line x1={margin.left} x2={width - margin.right} y1={y} y2={y} className="price-grid-line" />
              <text x={margin.left - 10} y={y + 4} textAnchor="end" className="price-axis-label">
                {formatYen(value)}
              </text>
            </g>
          );
        })}
        {xTickIndexes.map((index) => (
          <text
            key={`${index}-${points[index].ts.toISOString()}`}
            x={xFor(index)}
            y={height - 16}
            textAnchor="middle"
            dominantBaseline="hanging"
            className="price-axis-label"
          >
            {dateText(points[index].ts)}
          </text>
        ))}
        {points.length > 1 ? <polyline points={line} className="price-line" /> : null}
        {points.map((point, index) => (
          <circle key={`${point.ts.toISOString()}-${index}`} cx={xFor(index)} cy={yFor(point.price)} r="5">
            <title>{`${dateText(point.ts)} · ${formatYen(point.price)}`}</title>
          </circle>
        ))}
      </svg>
    </div>
  );
}

/** Extract a card/variant id from an id or image URL/filename. */
function extractVariantId(input: string): string {
  const raw = String(input || "").trim();
  if (!raw) return "";

  const tail = (() => {
    try {
      const u = new URL(raw);
      return decodeURIComponent(u.pathname.split("/").pop() || "");
    } catch {
      const seg = raw.split("/").pop() || raw;
      return decodeURIComponent(seg.split("?")[0] || "");
    }
  })();

  // ST01-002-P1.png / ST01-002_p1.png / DON17-10163.png
  const file = tail.replace(/\.png$/i, "");
  const don = file.match(/^(DON[A-Za-z0-9]*-\d{3,5})(?:[_-]([A-Za-z]*)(\d+))?$/i);
  if (don) {
    const base = don[1].toUpperCase();
    const letter = (don[2] || "").toUpperCase();
    const num = don[3] || "";
    if (!letter && !num) return base;
    return `${base}-${letter || "P"}${num}`;
  }
  const m = file.match(/^([A-Za-z]{2,4}\d{0,2}-\d{3})(?:[_-]([A-Za-z]*)(\d+))?$/i);
  if (m) {
    const base = m[1].toUpperCase();
    const letter = (m[2] || "").toUpperCase();
    const num = m[3] || "";
    if (!letter && !num) return base;
    return `${base}-${letter || "P"}${num}`;
  }

  // Already an id like ST01-002 / ST01-002-P1 / DON17-10163
  const id = normalizeCardId(raw);
  if (/^DON[A-Z0-9]*-\d{3,5}(?:-[A-Z]*\d+)?$/i.test(id)) return id.toUpperCase();
  if (/^[A-Z]{2,4}\d{0,2}-\d{3}(?:-[A-Z]*\d+)?$/i.test(id)) return id.toUpperCase();
  return "";
}

function variantMeta(input: string, fallbackBaseId: string): VariantMeta | null {
  const variantId = extractVariantId(input);
  if (!variantId) return null;
  const baseId = toBaseCardId(variantId) || fallbackBaseId;
  if (toBaseCardId(baseId) !== toBaseCardId(fallbackBaseId)) return null;

  const suffix = variantId.slice(baseId.length); // "" or "-P1" / "-R1"
  if (!suffix) {
    return { baseId, variantId: baseId, sortKey: "0-" };
  }
  const m = suffix.match(/^-([A-Z]*)(\d+)$/i);
  if (!m) {
    return { baseId, variantId, sortKey: `9-${suffix}` };
  }
  const letter = (m[1] || "P").toUpperCase();
  const num = String(m[2] || "0").padStart(4, "0");
  // P before R before others; number ascending
  const letterRank = letter === "P" ? "1" : letter === "R" ? "2" : "3";
  return { baseId, variantId, sortKey: `${letterRank}-${letter}-${num}` };
}

export function CardDetailClient({
  cardId,
  picked,
  pickedVariant,
}: {
  cardId: string;
  picked?: string;
  pickedVariant?: string;
}) {
  const { t, lang } = useI18n();
  const router = useRouter();
  const { token, isLoggedIn, ready, requestLogin } = useAuth();
  const deck = useDeck();
  const [card, setCard] = useState<Card | null>(null);
  const [error, setError] = useState("");
  const [activeVariantId, setActiveVariantId] = useState("");
  const [price, setPrice] = useState<CardPriceResponse | null>(null);
  const [priceLoading, setPriceLoading] = useState(false);
  const [ownedQty, setOwnedQty] = useState(0);

  const baseId = useMemo(() => toBaseCardId(cardId), [cardId]);
  const selectedVariantId = useMemo(() => {
    return (
      extractVariantId(pickedVariant || "") ||
      extractVariantId(picked || "") ||
      extractVariantId(cardId) ||
      baseId
    );
  }, [pickedVariant, picked, cardId, baseId]);

  function goBack() {
    if (typeof window !== "undefined" && window.history.length > 1) {
      router.back();
      return;
    }
    router.push("/search");
  }

  // From search wall: start at top. Returning from tournaments: restore saved Y.
  useLayoutEffect(() => {
    const path =
      typeof window !== "undefined"
        ? window.location.pathname
        : `/cards/${encodeURIComponent(cardId)}`;
    const target = readPathScrollTarget(path);
    if (target.y > 0 || target.anchor) {
      requestScrollRestore(target, () => clearCardDetailScroll(path));
      return;
    }
    window.scrollTo({ top: 0, behavior: "auto" });
  }, [cardId]);

  useEffect(() => {
    let cancelled = false;
    setError("");
    setActiveVariantId(selectedVariantId);
    // DON cards: load by full id (base truncation would break DON17-10163 → DON17-101).
    // Other cards: load by base id so sibling variants are complete.
    const loadId = isDonCardId(cardId) ? normalizeCardId(cardId) || selectedVariantId : baseId;
    const fallbackId = normalizeCardId(cardId) || selectedVariantId;
    fetchCard(loadId, false)
      .catch(() => fetchCard(loadId, false))
      .catch((e) => {
        if (fallbackId && fallbackId !== loadId) return fetchCard(fallbackId, false);
        throw e;
      })
      .then((res) => {
        if (cancelled) return;
        setCard(res.card);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [baseId, cardId, selectedVariantId]);

  const isDonCard = useMemo(() => {
    const id = card?.id || cardId || "";
    return isDonCardId(id) || String(card?.card_type || "").toLowerCase() === "don";
  }, [card?.id, card?.card_type, cardId]);

  const displayCardSets = useMemo(() => {
    const vid = normalizeCardId(activeVariantId || selectedVariantId || card?.id || "");
    const byVariant = card?.variant_card_sets || {};
    // Per-illustration scraped source only — never inherit base pack onto unknown parallels.
    if (vid && Object.prototype.hasOwnProperty.call(byVariant, vid)) {
      return byVariant[vid] || [];
    }
    if (vid && normalizeCardId(card?.id || "") === vid) {
      return card?.card_sets || [];
    }
    if (vid && toBaseCardId(vid) !== vid) {
      return [];
    }
    return card?.card_sets || [];
  }, [activeVariantId, selectedVariantId, card?.id, card?.card_sets, card?.variant_card_sets]);

  useEffect(() => {
    const priceCardId = activeVariantId || selectedVariantId;
    if (!priceCardId) return;
    let cancelled = false;
    setPrice(null);
    setPriceLoading(true);
    fetchCardPrice(priceCardId)
      .then((result) => {
        if (!cancelled) setPrice(result);
      })
      .catch(() => {
        if (!cancelled) setPrice(null);
      })
      .finally(() => {
        if (!cancelled) setPriceLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeVariantId, selectedVariantId]);

  useEffect(() => {
    const id = card?.id || "";
    if (!ready || !isLoggedIn || !token || !id) {
      setOwnedQty(0);
      return;
    }
    let cancelled = false;
    fetchCollection(token)
      .then((res) => {
        if (cancelled) return;
        setOwnedQty(Math.max(0, Math.floor(Number((res.cards || {})[id]) || 0)));
      })
      .catch(() => {
        if (!cancelled) setOwnedQty(0);
      });
    return () => {
      cancelled = true;
    };
  }, [ready, isLoggedIn, token, card?.id]);

  const thumbVariantIds = useMemo(() => {
    if (!card) return [] as string[];
    // DON cards have no parallel siblings under a shared OP-style base id.
    if (isDonCardId(card.id) || String(card.card_type || "").toLowerCase() === "don") {
      return [] as string[];
    }
    const byId = new Map<string, VariantMeta>();

    const imageStem = (raw: string) => {
      const text = String(raw || "").trim();
      if (!text) return "";
      try {
        const u = new URL(text);
        return decodeURIComponent((u.pathname.split("/").pop() || "").split("?")[0] || "").toLowerCase();
      } catch {
        const seg = text.split("/").pop() || text;
        return decodeURIComponent(seg.split("?")[0] || "").toLowerCase();
      }
    };

    const baseImgStem = imageStem(card.img_full_url || card.img_url || card.img_local_url || "");

    const add = (raw: string) => {
      const meta = variantMeta(raw, baseId);
      if (!meta) return;
      // Official CDN often names the only printing OP05-062_p1.png — not a parallel.
      if (meta.variantId !== baseId && baseImgStem && imageStem(raw) === baseImgStem) return;
      if (!byId.has(meta.variantId)) byId.set(meta.variantId, meta);
    };

    // Rule: same prefix (base) goes into thumbs.
    add(baseId); // always include first/base card
    add(card.id);
    add(selectedVariantId);
    for (const u of card.alt_image_urls || []) add(u);

    return Array.from(byId.values())
      .sort((a, b) => a.sortKey.localeCompare(b.sortKey) || a.variantId.localeCompare(b.variantId))
      .map((m) => m.variantId);
  }, [card, baseId, selectedVariantId]);

  if (error) {
    return (
      <div className="stack">
        <button type="button" className="ghost" onClick={goBack} style={{ alignSelf: "flex-start" }}>
          {t("detail.back")}
        </button>
        <p style={{ color: "#fca5a5" }}>{error}</p>
      </div>
    );
  }
  if (!card) return <p className="muted">…</p>;

  const name = isDonCard
    ? localizeDonCardName(card.name, card.name_en, lang) || displayCardId(card.id)
    : localizeCardName(card.name, card.name_en, lang) || displayCardId(card.id);
  const rawEffect = localizeCardText(card.effect, lang, card.effect_en);
  const rawTrigger = localizeCardText(card.trigger || card.trigger_en, lang, card.trigger_en);
  const { body: effect, trigger } = (() => {
    const effectText = String(rawEffect || "").trim();
    let triggerText = String(rawTrigger || "").trim();
    if (!triggerText) {
      const m = effectText.match(/(?:^|\n)\s*((?:【觸發器】|【触发】|\[Trigger\])[^\n]*)/);
      if (m) triggerText = m[1].trim();
    }
    let body = effectText;
    if (triggerText && body.includes(triggerText)) {
      body = body.replace(triggerText, "").replace(/\n{2,}/g, "\n").trim();
    }
    body = formatEffectLines(body);
    return { body, trigger: triggerText };
  })();
  const colors =
    lang === "en"
      ? card.colors_en?.length
        ? card.colors_en
        : localizeFilterTokens("color", card.colors, lang)
      : localizeFilterTokens("color", card.colors?.length ? card.colors : card.colors_en, lang);
  const type =
    lang === "en"
      ? card.card_type_en ||
        localizeFilterToken("type", card.card_type || "", lang) ||
        preferLangText(card.card_type, "en")
      : localizeFilterToken("type", card.card_type || card.card_type_en || "", lang) ||
        localizeCardText(card.card_type, lang);
  const attrs =
    lang === "en"
      ? card.attributes_en?.length
        ? card.attributes_en
        : localizeFilterTokens("attr", card.attributes, lang)
      : localizeFilterTokens(
          "attr",
          card.attributes?.length ? card.attributes : card.attributes_en,
          lang,
        );
  const traits = localizeCardList(card.traits, lang, card.traits_en);

  async function onCollect(delta: 1 | -1) {
    if (!isLoggedIn || !token) {
      requestLogin();
      return;
    }
    try {
      const res =
        delta > 0 ? await collectionAdd(token, card!.id, 1) : await collectionRemove(token, card!.id, 1);
      setOwnedQty(Math.max(0, Math.floor(Number((res.cards || {})[card!.id]) || 0)));
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="stack">
      <button type="button" className="ghost" onClick={goBack} style={{ alignSelf: "flex-start" }}>
        {t("detail.back")}
      </button>
      <div className="detail-grid">
        <div className="detail-img">
          <h2 style={{ marginBottom: 8 }}>{t("detail.images")}</h2>
          <CardImg
            className="detail-main-img"
            cardId={activeVariantId || selectedVariantId}
            alt={name || displayCardId(card.id)}
            loading="eager"
          />
          {thumbVariantIds.length > 0 ? (
            <div className="detail-thumbs">
              {thumbVariantIds.map((vid) => {
                return (
                  <button
                    key={vid}
                    type="button"
                    className={`detail-thumb ${(activeVariantId || selectedVariantId) === vid ? "active" : ""}`}
                    onClick={() => setActiveVariantId(vid)}
                    title={displayCardId(vid)}
                  >
                    <CardImg cardId={vid} alt={displayCardId(vid)} />
                  </button>
                );
              })}
            </div>
          ) : null}
        </div>
        <div className="detail-info">
          <h2 style={{ marginBottom: 8 }}>{t("detail.info")}</h2>
          <dl>
            {!isDonCard ? (
              <>
                <dt>{t("detail.id")}</dt>
                <dd>{displayCardId(activeVariantId || selectedVariantId || card.id)}</dd>
              </>
            ) : null}
            <dt>{t("detail.name")}</dt>
            <dd>{name || "-"}</dd>
            <dt>{t("detail.rarity")}</dt>
            <dd>{localizeFilterToken("rarity", card.rarity || "", lang) || "-"}</dd>
            <dt>{t("detail.type")}</dt>
            <dd>{type || "-"}</dd>
            {!isDonCard ? (
              <>
                <dt>{t("detail.color")}</dt>
                <dd>{(colors || []).join(", ") || "-"}</dd>
                <dt>{t("detail.cost")}</dt>
                <dd>{card.cost ?? "-"}</dd>
                <dt>{t("detail.power")}</dt>
                <dd>{card.power ?? "-"}</dd>
                <dt>{t("detail.counter")}</dt>
                <dd>{card.counter ?? "-"}</dd>
                <dt>{t("detail.block")}</dt>
                <dd>{card.block_number ?? "-"}</dd>
                <dt>{t("detail.attr")}</dt>
                <dd>{(attrs || []).join(", ") || "-"}</dd>
                <dt>{t("detail.traits")}</dt>
                <dd>{(traits || []).join(", ") || "-"}</dd>
              </>
            ) : null}
            <dt>{t("detail.source")}</dt>
            <dd>
              {localizeCardSources(displayCardSets, lang).join(lang === "en" ? ", " : "、") || "-"}
            </dd>
          </dl>
          <div className="detail-actions">
            {!isDonCard
              ? (() => {
                  const id = activeVariantId || selectedVariantId || card.id;
                  const qty = deck.qtyOf(id);
                  const asLeader = Boolean(card.card_type && /leader|领袖|領袖/i.test(String(card.card_type)));
                  return (
                    <>
                      <button type="button" onClick={() => deck.addCard(id, card.card_type)}>
                        {t("wall.deck_add")}
                        {qty > 0 ? ` (${qty})` : ""}
                      </button>
                      <button
                        type="button"
                        className="btn-remove"
                        disabled={qty <= 0}
                        onClick={() => deck.removeCard(id, asLeader)}
                      >
                        {t("wall.deck_rm")}
                      </button>
                    </>
                  );
                })()
              : null}
            <button type="button" className="btn-add" onClick={() => onCollect(1)}>
              {t("detail.col_add")}
              {ownedQty > 0 ? ` (${ownedQty})` : ""}
            </button>
            <button
              type="button"
              className="btn-remove"
              onClick={() => onCollect(-1)}
              disabled={ownedQty <= 0}
            >
              {t("detail.col_rm")}
            </button>
          </div>
          {!isDonCard && effect ? (
            <div>
              <h3 style={{ margin: "0.5rem 0" }}>{t("detail.effect")}</h3>
              <p style={{ whiteSpace: "pre-wrap", lineHeight: 1.45 }}>{effect}</p>
            </div>
          ) : null}
          {!isDonCard && trigger ? (
            <div>
              <h3 style={{ margin: "0.5rem 0" }}>{t("detail.trigger")}</h3>
              <p style={{ whiteSpace: "pre-wrap", lineHeight: 1.45, color: "#fde68a" }}>{trigger}</p>
            </div>
          ) : null}
          {!isDonCard ? (
            <CardDetailExtras
              cardId={normalizeCardId(activeVariantId || selectedVariantId || card.id) || card.id}
              sections="comments"
            />
          ) : null}
          <section className="price-panel">
            <div className="price-panel-head">
              <div>
                <h3>{t("detail.market_price")}</h3>
                <p className="muted">
                  {isDonCard
                    ? t("detail.price_currency")
                    : `${displayCardId(activeVariantId || selectedVariantId || card.id)} · ${t("detail.price_currency")}`}
                </p>
              </div>
              <div className="price-current">
                {priceLoading
                  ? "…"
                  : price?.current_price != null
                    ? formatYen(price.current_price)
                    : t("detail.price_unavailable")}
              </div>
            </div>
            <p className="price-disclaimer">{t("detail.price_disclaimer")}</p>
            {price && price.history.length > 0 ? (
              <>
                <PriceChart history={price.history} lang={lang} />
                {price.history.length === 1 ? (
                  <p className="price-note">{t("detail.price_one_point")}</p>
                ) : null}
              </>
            ) : !priceLoading ? (
              <p className="price-note">{t("detail.price_no_history")}</p>
            ) : null}
          </section>
        </div>
      </div>
      {!isDonCard ? (
        <CardDetailExtras
          cardId={toBaseCardId(activeVariantId || selectedVariantId || card.id)}
          sections="tournaments"
        />
      ) : null}
    </div>
  );
}
