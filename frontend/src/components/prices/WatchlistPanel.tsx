"use client";

import { useCallback, useEffect, useState } from "react";
import { type BatchPriceFields } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { formatYen, loadUnitPrices, sumPricedCopies } from "@/lib/priceCalc";
import { clearWatchlist, isOnWatchlist, removeFromWatchlist, WATCHLIST_MAX } from "@/lib/priceWatchlist";
import { PriceWallTile } from "./PriceWallTile";

type Props = {
  watchlist: string[];
  onWatchlistChange: (ids: string[]) => void;
};

export function WatchlistPanel({ watchlist, onWatchlistChange }: Props) {
  const { t } = useI18n();
  const [prices, setPrices] = useState<Record<string, BatchPriceFields>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    if (!watchlist.length) {
      setPrices({});
      return;
    }
    setLoading(true);
    setError("");
    try {
      const map = await loadUnitPrices(watchlist);
      setPrices(map);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setPrices({});
    } finally {
      setLoading(false);
    }
  }, [watchlist]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const qtyMap = Object.fromEntries(watchlist.map((id) => [id, 1]));
  const sum = sumPricedCopies(qtyMap, prices);

  function remove(cardId: string) {
    if (!window.confirm(t("prices.watch_remove_confirm"))) return;
    onWatchlistChange(removeFromWatchlist(cardId));
  }

  function clearAll() {
    if (!watchlist.length) return;
    if (!window.confirm(t("prices.watch_clear_confirm", { count: watchlist.length }))) return;
    onWatchlistChange(clearWatchlist());
  }

  return (
    <div className="stack">
      <div className="deck-panel">
        <div className="deck-section-head">
          <div>
            <h2 className="deck-section-title">{t("prices.watch_title")}</h2>
            <p className="deck-section-sub muted">
              {t("prices.watch_hint", { count: watchlist.length, max: WATCHLIST_MAX })}
            </p>
            {watchlist.length ? (
              <p className="muted" style={{ marginTop: "0.35rem" }}>
                {t("prices.assets_sum", {
                  total: formatYen(sum.total),
                  priced: sum.pricedCopies,
                  missing: sum.missingCopies,
                })}
              </p>
            ) : null}
          </div>
          <div className="prices-watch-actions">
            <button type="button" className="btn-price" disabled={loading || !watchlist.length} onClick={() => void refresh()}>
              {loading ? t("prices.loading") : t("prices.refresh")}
            </button>
            <button type="button" className="btn-danger" disabled={!watchlist.length} onClick={clearAll}>
              {t("prices.watch_clear")}
            </button>
          </div>
        </div>
      </div>

      {error ? (
        <p className="error" style={{ color: "#fca5a5" }}>
          {error}
        </p>
      ) : null}

      {!watchlist.length ? (
        <p className="muted">{t("prices.watch_empty")}</p>
      ) : (
        <div className="price-wall">
          {watchlist.map((id) => (
            <PriceWallTile
              key={id}
              card={{ id }}
              price={prices[id]?.current_price}
              lastChecked={prices[id]?.last_checked}
              watched={isOnWatchlist(id, watchlist)}
              onToggleWatch={remove}
            />
          ))}
        </div>
      )}
    </div>
  );
}
