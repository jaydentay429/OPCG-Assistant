"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchBinder, fetchCollection, fetchDecks } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { displayCardId } from "@/lib/cardId";
import { useI18n } from "@/lib/i18n";
import { formatYen, loadUnitPrices, sumPricedCopies, unitPriceOf } from "@/lib/priceCalc";
import { readAssetsPrefs, saveAssetsPrefs } from "@/lib/pricesPrefs";
import type { BinderResponse, CollectionResponse, Deck } from "@/lib/types";

type TopRow = { id: string; qty: number; unit: number; line: number };

export function AssetsPanel() {
  const { t } = useI18n();
  const { token, isLoggedIn, ready } = useAuth();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [collection, setCollection] = useState<CollectionResponse | null>(null);
  const [decks, setDecks] = useState<Deck[]>([]);
  const [binder, setBinder] = useState<BinderResponse | null>(null);
  const [prices, setPrices] = useState<Record<string, { current_price?: number | null }>>({});
  const savedPrefs = useMemo(() => readAssetsPrefs(), []);
  const [showTop, setShowTop] = useState(savedPrefs.showTop);
  const [openDeckId, setOpenDeckId] = useState<string | null>(savedPrefs.openDeckId);

  useEffect(() => {
    saveAssetsPrefs({ showTop, openDeckId });
  }, [showTop, openDeckId]);

  const refresh = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError("");
    try {
      const [col, deckRes, bind] = await Promise.all([
        fetchCollection(token),
        fetchDecks(token),
        fetchBinder(token),
      ]);
      setCollection(col);
      setDecks(deckRes.decks || []);
      setBinder(bind);

      const ids = new Set<string>();
      for (const [id, qty] of Object.entries(col.cards || {})) {
        if (Number(qty) > 0) ids.add(id);
      }
      for (const d of deckRes.decks || []) {
        if (d.leader_card_id) ids.add(d.leader_card_id);
        for (const [id, qty] of Object.entries(d.cards || {})) {
          if (Number(qty) > 0) ids.add(id);
        }
      }
      for (const page of bind.pages || []) {
        for (const slot of page || []) {
          if (slot) ids.add(slot);
        }
      }
      const map = await loadUnitPrices([...ids]);
      setPrices(map);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    if (!ready || !isLoggedIn || !token) {
      setCollection(null);
      setDecks([]);
      setBinder(null);
      setPrices({});
      return;
    }
    void refresh();
  }, [ready, isLoggedIn, token, refresh]);

  const collectionSum = useMemo(
    () => sumPricedCopies(collection?.cards || {}, prices),
    [collection, prices],
  );

  const topCards = useMemo(() => {
    const rows: TopRow[] = [];
    for (const [id, rawQty] of Object.entries(collection?.cards || {})) {
      const qty = Math.max(0, Math.floor(Number(rawQty) || 0));
      if (!qty) continue;
      const unit = unitPriceOf(prices, id);
      if (unit == null) continue;
      rows.push({ id, qty, unit, line: unit * qty });
    }
    rows.sort((a, b) => b.line - a.line || b.unit - a.unit);
    return rows.slice(0, 20);
  }, [collection, prices]);

  const deckRows = useMemo(() => {
    return (decks || []).map((d) => {
      const qtyMap: Record<string, number> = { ...(d.cards || {}) };
      if (d.leader_card_id) {
        qtyMap[d.leader_card_id] = (qtyMap[d.leader_card_id] || 0) + 1;
      }
      const sum = sumPricedCopies(qtyMap, prices);
      return { deck: d, qtyMap, sum };
    });
  }, [decks, prices]);

  const binderPages = useMemo(() => {
    const pages = binder?.pages || [];
    const titles = binder?.page_titles || [];
    return pages.map((slots, idx) => {
      const qtyMap: Record<string, number> = {};
      for (const slot of slots || []) {
        if (!slot) continue;
        qtyMap[slot] = (qtyMap[slot] || 0) + 1;
      }
      const sum = sumPricedCopies(qtyMap, prices);
      const title = (titles[idx] || "").trim() || t("prices.assets_page", { n: idx + 1 });
      return { idx, title, qtyMap, sum, filled: Object.values(qtyMap).reduce((a, b) => a + b, 0) };
    });
  }, [binder, prices, t]);

  const binderTotal = useMemo(() => {
    const qtyMap: Record<string, number> = {};
    for (const p of binderPages) {
      for (const [id, qty] of Object.entries(p.qtyMap)) {
        qtyMap[id] = (qtyMap[id] || 0) + qty;
      }
    }
    return sumPricedCopies(qtyMap, prices);
  }, [binderPages, prices]);

  if (!ready) {
    return <p className="muted">{t("prices.loading")}</p>;
  }

  if (!isLoggedIn) {
    return (
      <div className="deck-panel">
        <p className="muted">{t("prices.assets_login")}</p>
      </div>
    );
  }

  return (
    <div className="stack prices-assets">
      <div className="prices-toolbar">
        <p className="muted">{loading ? t("prices.loading") : t("prices.assets_hint")}</p>
        <button type="button" className="btn-price" disabled={loading} onClick={() => void refresh()}>
          {t("prices.refresh")}
        </button>
      </div>
      {error ? (
        <p className="error" style={{ color: "#fca5a5" }}>
          {error}
        </p>
      ) : null}

      <section className="deck-panel">
        <div className="deck-section-head">
          <div>
            <h2 className="deck-section-title">{t("prices.assets_collection")}</h2>
            <p className="deck-section-sub muted">
              {t("prices.assets_sum", {
                total: formatYen(collectionSum.total),
                priced: collectionSum.pricedCopies,
                missing: collectionSum.missingCopies,
              })}
            </p>
          </div>
          <button type="button" className="secondary" onClick={() => setShowTop((v) => !v)}>
            {showTop ? t("prices.assets_hide_top") : t("prices.assets_show_top")}
          </button>
        </div>
        {showTop ? (
          topCards.length ? (
            <ul className="prices-asset-list">
              {topCards.map((row) => (
                <li key={row.id}>
                  <span>
                    {displayCardId(row.id)} ×{row.qty}
                  </span>
                  <span className="price-tile-yen">
                    {formatYen(row.unit)} → {formatYen(row.line)}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">{t("prices.assets_empty_priced")}</p>
          )
        ) : null}
      </section>

      <section className="deck-panel">
        <div className="deck-section-head">
          <div>
            <h2 className="deck-section-title">{t("prices.assets_decks")}</h2>
            <p className="deck-section-sub muted">{t("prices.assets_decks_sub")}</p>
          </div>
        </div>
        {!deckRows.length ? (
          <p className="muted">{t("prices.assets_no_decks")}</p>
        ) : (
          <ul className="prices-asset-list">
            {deckRows.map(({ deck, qtyMap, sum }) => {
              const open = openDeckId === deck.id;
              return (
                <li key={deck.id} className="prices-asset-deck">
                  <button type="button" className="prices-asset-deck-btn" onClick={() => setOpenDeckId(open ? null : deck.id)}>
                    <span>{deck.name || t("prices.assets_unnamed_deck")}</span>
                    <span className="price-tile-yen">{formatYen(sum.total)}</span>
                  </button>
                  {open ? (
                    <ul className="prices-asset-sublist">
                      {Object.entries(qtyMap)
                        .filter(([, q]) => Number(q) > 0)
                        .sort((a, b) => {
                          const ua = unitPriceOf(prices, a[0]) ?? -1;
                          const ub = unitPriceOf(prices, b[0]) ?? -1;
                          return ub - ua;
                        })
                        .map(([id, qty]) => {
                          const unit = unitPriceOf(prices, id);
                          return (
                            <li key={id}>
                              <span>
                                {displayCardId(id)} ×{qty}
                              </span>
                              <span className={unit == null ? "muted" : "price-tile-yen"}>
                                {unit == null ? t("prices.na") : `${formatYen(unit)} → ${formatYen(unit * qty)}`}
                              </span>
                            </li>
                          );
                        })}
                      <li className="muted">
                        {t("price.missing_note", { missing: sum.missingCopies })}
                      </li>
                    </ul>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section className="deck-panel">
        <div className="deck-section-head">
          <div>
            <h2 className="deck-section-title">{t("prices.assets_binder")}</h2>
            <p className="deck-section-sub muted">
              {t("prices.assets_sum", {
                total: formatYen(binderTotal.total),
                priced: binderTotal.pricedCopies,
                missing: binderTotal.missingCopies,
              })}
            </p>
          </div>
        </div>
        {!binderPages.some((p) => p.filled > 0) ? (
          <p className="muted">{t("prices.assets_binder_empty")}</p>
        ) : (
          <ul className="prices-asset-list">
            {binderPages
              .filter((p) => p.filled > 0)
              .map((p) => (
                <li key={p.idx}>
                  <span>
                    {p.title}（{p.filled}）
                  </span>
                  <span className="price-tile-yen">{formatYen(p.sum.total)}</span>
                </li>
              ))}
          </ul>
        )}
      </section>
    </div>
  );
}
