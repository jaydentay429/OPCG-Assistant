"use client";

import Link from "next/link";
import { displayCardId, isDonCardId } from "@/lib/cardId";
import { localizeCardName, localizeDonCardName } from "@/lib/cardLocale";
import { useI18n } from "@/lib/i18n";
import { formatYen } from "@/lib/priceCalc";
import { flushCurrentScroll } from "@/lib/scrollRestore";
import { CardImg } from "../CardImg";

export type PriceWallCard = {
  id: string;
  name?: string | null;
  name_en?: string | null;
  img_local_url?: string | null;
};

type Props = {
  card: PriceWallCard;
  price?: number | null;
  lastChecked?: string | null;
  watched?: boolean;
  onToggleWatch?: (cardId: string) => void;
};

function formatChecked(raw: string | null | undefined, fallback: string): string | null {
  if (!raw) return null;
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return null;
  try {
    return `${fallback} ${d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}`;
  } catch {
    return null;
  }
}

export function PriceWallTile({ card, price, lastChecked, watched, onToggleWatch }: Props) {
  const { t, lang } = useI18n();
  const yen = formatYen(price);
  const isDon = isDonCardId(card.id);
  let name = isDon
    ? localizeDonCardName(card.name, card.name_en, lang) || displayCardId(card.id)
    : localizeCardName(card.name, card.name_en, lang) || displayCardId(card.id);
  // Belt-and-suspenders: Chinese UI must never show Loki/Gloriosa when API has 洛基/嘉蘭.
  if (!isDon && lang !== "en") {
    const official = String(card.name || "").trim();
    const looksEnglish = name === String(card.name_en || "").trim() || /^[A-Za-z0-9][A-Za-z0-9 .,'!?\-&]*$/.test(name);
    if (looksEnglish && /[\u4e00-\u9fff]/.test(official)) {
      name = localizeCardName(official, null, lang) || official;
    }
  }
  const synced = formatChecked(lastChecked, t("prices.synced_prefix"));

  return (
    <div className="price-tile-wrap" data-scroll-anchor={card.id}>
      <Link
        href={`/cards/${encodeURIComponent(card.id)}?pickedVariant=${encodeURIComponent(card.id)}`}
        className="price-tile"
        title={t("prices.open_detail")}
        scroll={false}
        onPointerDown={() => flushCurrentScroll(card.id)}
        onClick={() => flushCurrentScroll(card.id)}
      >
        <div className="price-tile-art">
          <CardImg cardId={card.id} alt={name} localUrl={card.img_local_url || undefined} />
        </div>
        <div className="price-tile-meta">
          {isDonCardId(card.id) ? null : <strong>{displayCardId(card.id)}</strong>}
          <span className="price-tile-name">{name}</span>
          <span className={`price-tile-yen${price != null && Number.isFinite(price) ? "" : " muted"}`}>
            {price != null && Number.isFinite(Number(price)) ? yen : t("prices.na")}
          </span>
          {synced ? <span className="price-tile-sync muted">{synced}</span> : null}
        </div>
      </Link>
      {onToggleWatch ? (
        <button
          type="button"
          className={`price-watch-btn${watched ? " is-on" : ""}`}
          onClick={() => onToggleWatch(card.id)}
          title={watched ? t("prices.watch_remove") : t("prices.watch_add")}
        >
          {watched ? t("prices.watch_on") : t("prices.watch_add_short")}
        </button>
      ) : null}
    </div>
  );
}
