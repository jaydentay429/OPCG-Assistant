"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { collectionAdd, collectionRemove, fetchCollection } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useDeck } from "@/lib/deck";
import { useI18n } from "@/lib/i18n";
import { localizeCardName, localizeDonCardName } from "@/lib/cardLocale";
import { displayCardId, isDonCardId } from "@/lib/cardId";
import type { FilterCard } from "@/lib/types";
import { flushCurrentScroll } from "@/lib/scrollRestore";
import { CardImg } from "./CardImg";

export function CardWallSkeleton({ n = 10 }: { n?: number }) {
  return (
    <div className="card-wall" aria-hidden="true">
      {Array.from({ length: n }, (_, i) => (
        <article key={i} className="card-tile card-tile-skeleton">
          <div className="thumb" />
          <div className="id">&nbsp;</div>
          <div className="actions">
            <span />
            <span />
          </div>
        </article>
      ))}
    </div>
  );
}

export function CardWall({ cards }: { cards: FilterCard[] }) {
  const { t, lang } = useI18n();
  const { token, isLoggedIn, ready, requestLogin } = useAuth();
  const deck = useDeck();
  const [owned, setOwned] = useState<Record<string, number>>({});

  useEffect(() => {
    if (!ready || !isLoggedIn || !token) {
      setOwned({});
      return;
    }
    let cancelled = false;
    fetchCollection(token)
      .then((res) => {
        if (!cancelled) setOwned(res.cards || {});
      })
      .catch(() => {
        if (!cancelled) setOwned({});
      });
    return () => {
      cancelled = true;
    };
  }, [ready, isLoggedIn, token]);

  async function onCollect(id: string, delta: 1 | -1) {
    if (!isLoggedIn || !token) {
      requestLogin();
      return;
    }
    try {
      const res =
        delta > 0 ? await collectionAdd(token, id, 1) : await collectionRemove(token, id, 1);
      setOwned(res.cards || {});
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
  }

  function onDeck(id: string, delta: 1 | -1, cardType?: string | null) {
    if (delta > 0) {
      const r = deck.addCard(id, cardType);
      if (!r.ok && r.msg) alert(r.msg);
    } else {
      deck.removeCard(id, Boolean(cardType && /leader|领袖|領袖/i.test(String(cardType))));
    }
  }

  if (!cards.length) {
    return <p className="muted">{t("filter.no_results")}</p>;
  }

  return (
    <div className="card-wall">
      {cards.map((c) => {
        const pickedVariant = c.id;
        const qty = deck.qtyOf(c.id);
        const colQty = Math.max(0, Math.floor(Number(owned[c.id]) || 0));
        const isDon = isDonCardId(c.id) || String(c.card_type || "").toLowerCase() === "don";
        const displayName = isDon
          ? localizeDonCardName(c.name, c.name_en, lang) || displayCardId(c.id)
          : localizeCardName(c.name, c.name_en, lang) || displayCardId(c.id);
        return (
          <article key={c.id} className="card-tile" data-scroll-anchor={c.id}>
            <Link
              href={`/cards/${encodeURIComponent(c.id)}?pickedVariant=${encodeURIComponent(pickedVariant)}`}
              className="thumb"
              scroll={false}
              onPointerDown={() => flushCurrentScroll(c.id)}
              onClick={() => flushCurrentScroll(c.id)}
            >
              <CardImg cardId={c.id} alt={displayName} localUrl={c.img_local_url} />
            </Link>
            {isDon ? null : (
              <div className="id" title={displayCardId(c.id)}>
                {displayCardId(c.id)}
              </div>
            )}
            {isDon ? <div className="id" title={displayName}>{displayName}</div> : null}
            <div className="actions">
              <button type="button" onClick={() => onDeck(c.id, 1, c.card_type)}>
                {t("wall.deck_add")}
                {qty > 0 ? ` (${qty})` : ""}
              </button>
              <button
                type="button"
                className="btn-remove"
                onClick={() => onDeck(c.id, -1, c.card_type)}
                disabled={qty <= 0}
              >
                {t("wall.deck_rm")}
              </button>
              <button type="button" className="btn-add" onClick={() => onCollect(c.id, 1)}>
                {t("wall.col_add")}
                {colQty > 0 ? ` (${colQty})` : ""}
              </button>
              <button
                type="button"
                className="btn-remove"
                onClick={() => onCollect(c.id, -1)}
                disabled={colQty <= 0}
              >
                {t("wall.col_rm")}
              </button>
            </div>
          </article>
        );
      })}
    </div>
  );
}
