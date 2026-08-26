"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { fetchFilterCards, fetchFilterOptions, fetchPricesBatch, type BatchPriceFields } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import {
  addToWatchlist,
  isOnWatchlist,
  removeFromWatchlist,
} from "@/lib/priceWatchlist";
import { readMarketPrefs, saveMarketPrefs, type MarketSort } from "@/lib/pricesPrefs";
import {
  consumeSkipScrollRestore,
  requestScrollRestore,
  scrollYForPersist,
} from "@/lib/scrollRestore";
import type { FilterCard, FilterOptions, FilterState } from "@/lib/types";
import { FilterBar } from "../FilterBar";
import { SearchBar } from "../SearchBar";
import { PriceWallTile } from "./PriceWallTile";

const PAGE_SIZE = 70;

type SortMode = MarketSort;

function filtersToQuery(
  f: FilterState,
  q: string,
  page: number,
  sort: SortMode,
  priceMin: string,
  priceMax: string,
) {
  const pMin = priceMin.trim() ? Number(priceMin) : undefined;
  const pMax = priceMax.trim() ? Number(priceMax) : undefined;

  return {
    colors: f.colors.join(",") || undefined,
    costs: f.costs.join(",") || undefined,
    counters: f.counters.join(",") || undefined,
    powers: f.powers.join(",") || undefined,
    card_types: f.card_types.join(",") || undefined,
    attributes: f.attributes.join(",") || undefined,
    keywords: (f.keywords || []).join(",") || undefined,
    serieses: f.serieses.join(",") || undefined,
    rarities: f.rarities.join(",") || undefined,
    blocks: f.blocks.join(",") || undefined,
    q: q.trim() || undefined,
    sort,
    price_min: pMin != null && Number.isFinite(pMin) ? pMin : undefined,
    price_max: pMax != null && Number.isFinite(pMax) ? pMax : undefined,
    offset: (page - 1) * PAGE_SIZE,
    limit: PAGE_SIZE,
  };
}

type Props = {
  watchlist: string[];
  onWatchlistChange: (ids: string[]) => void;
};

export function MarketPanel({ watchlist, onWatchlistChange }: Props) {
  const { t } = useI18n();
  const saved = useMemo(() => readMarketPrefs(), []);
  const [q, setQ] = useState(saved.q);
  const [debouncedQ, setDebouncedQ] = useState(saved.q);
  const [searchTick, setSearchTick] = useState(0);
  const [filters, setFilters] = useState<FilterState>(saved.filters);
  const [options, setOptions] = useState<FilterOptions | null>(null);
  const [cards, setCards] = useState<FilterCard[]>([]);
  const [prices, setPrices] = useState<Record<string, BatchPriceFields>>({});
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(saved.page);
  const [sort, setSort] = useState<SortMode>(saved.sort);
  const [priceMin, setPriceMin] = useState(saved.priceMin);
  const [priceMax, setPriceMax] = useState(saved.priceMax);
  const [loading, setLoading] = useState(false);
  const [priceLoading, setPriceLoading] = useState(false);
  const [error, setError] = useState("");
  const pendingScrollRef = useRef(saved.scrollY);
  const pendingAnchorRef = useRef(saved.scrollAnchor || "");
  const restoreOnceRef = useRef(false);
  const queryKey = useMemo(
    () => JSON.stringify([debouncedQ, filters, sort, priceMin, priceMax]),
    [debouncedQ, filters, sort, priceMin, priceMax],
  );
  const lastQueryKeyRef = useRef(queryKey);

  useEffect(() => {
    if (consumeSkipScrollRestore()) {
      pendingScrollRef.current = 0;
      pendingAnchorRef.current = "";
    }
  }, []);

  useEffect(() => {
    const tmr = setTimeout(() => setDebouncedQ(q), 220);
    return () => clearTimeout(tmr);
  }, [q]);

  useEffect(() => {
    fetchFilterOptions()
      .then(setOptions)
      .catch(() => setOptions({ series: [], rarities: [], blocks: [] }));
  }, []);

  // Only a real query change resets paging, so the restored page survives remounts.
  useEffect(() => {
    if (lastQueryKeyRef.current === queryKey) return;
    lastQueryKeyRef.current = queryKey;
    setPage(1);
    pendingScrollRef.current = 0;
    pendingAnchorRef.current = "";
    restoreOnceRef.current = false;
  }, [queryKey]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    const query = filtersToQuery(filters, debouncedQ, page, sort, priceMin, priceMax);
    fetchFilterCards(query)
      .then((res) => {
        if (cancelled) return;
        setCards(res.cards);
        setTotal(res.total);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
        setCards([]);
        setTotal(0);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [filters, debouncedQ, page, sort, priceMin, priceMax, searchTick]);

  useEffect(() => {
    const ids = cards.map((c) => c.id);
    if (!ids.length) {
      setPrices({});
      return;
    }
    let cancelled = false;
    setPriceLoading(true);
    fetchPricesBatch(ids)
      .then((map) => {
        if (!cancelled) setPrices(map || {});
      })
      .catch(() => {
        if (!cancelled) setPrices({});
      })
      .finally(() => {
        if (!cancelled) setPriceLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [cards]);

  const totalPages = useMemo(() => Math.max(1, Math.ceil(total / PAGE_SIZE)), [total]);

  const persistPrefs = (scrollY?: number, anchor?: string) => {
    const y = scrollYForPersist(
      pendingScrollRef.current,
      scrollY ?? (typeof window !== "undefined" ? window.scrollY || 0 : 0),
    );
    if (typeof anchor === "string" && anchor.trim()) {
      pendingAnchorRef.current = anchor.trim();
    }
    saveMarketPrefs({
      q,
      filters,
      sort,
      priceMin,
      priceMax,
      page,
      scrollY: y,
      scrollAnchor: pendingAnchorRef.current || "",
    });
  };

  useEffect(() => {
    if (typeof window === "undefined") return;
    persistPrefs(window.scrollY || 0);
    const onScroll = () => persistPrefs(window.scrollY || 0);
    const flush = (e?: Event) => {
      const detail = (e as CustomEvent<{ y?: number; anchor?: string }> | undefined)?.detail;
      if (typeof detail?.anchor === "string" && detail.anchor) {
        pendingAnchorRef.current = detail.anchor;
      }
      persistPrefs(typeof detail?.y === "number" ? detail.y : window.scrollY || 0, detail?.anchor);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("pagehide", flush);
    window.addEventListener("opcg:flush-scroll", flush as EventListener);
    document.addEventListener("visibilitychange", flush);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("pagehide", flush);
      window.removeEventListener("opcg:flush-scroll", flush as EventListener);
      document.removeEventListener("visibilitychange", flush);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- persist latest fields only
  }, [q, filters, sort, priceMin, priceMax, page]);

  // Restore once after the wall has data — prefer the clicked card anchor.
  useLayoutEffect(() => {
    if (loading || restoreOnceRef.current) return;
    if (!pendingScrollRef.current && !pendingAnchorRef.current) return;
    if (!cards.length) return;
    restoreOnceRef.current = true;
    const y = pendingScrollRef.current;
    const anchor = pendingAnchorRef.current;
    requestScrollRestore({ y, anchor }, () => {
      pendingScrollRef.current = 0;
      pendingAnchorRef.current = "";
    });
  }, [loading, cards.length, page]);

  function toggleWatch(cardId: string) {
    const next = isOnWatchlist(cardId, watchlist)
      ? removeFromWatchlist(cardId)
      : addToWatchlist(cardId);
    onWatchlistChange(next);
  }

  return (
    <div className="stack">
      <SearchBar
        value={q}
        onChange={setQ}
        onClear={() => {
          setQ("");
          setDebouncedQ("");
          setSearchTick((n) => n + 1);
        }}
        onSubmit={() => {
          const next = q.trim();
          setQ(next);
          setDebouncedQ(next);
          setSearchTick((n) => n + 1);
        }}
      />
      <FilterBar options={options} value={filters} onChange={setFilters} />

      <div className="prices-toolbar">
        <p className="muted search-result-hint">
          {t("filter.filter_result", { total, size: PAGE_SIZE })}
          {loading || priceLoading ? ` ${t("prices.loading")}` : ""}
        </p>
        <div className="prices-market-controls">
          <label className="prices-range">
            <span className="muted">{t("prices.price_min")}</span>
            <input
              type="number"
              min={0}
              inputMode="numeric"
              value={priceMin}
              onChange={(e) => setPriceMin(e.target.value)}
              placeholder="0"
            />
          </label>
          <label className="prices-range">
            <span className="muted">{t("prices.price_max")}</span>
            <input
              type="number"
              min={0}
              inputMode="numeric"
              value={priceMax}
              onChange={(e) => setPriceMax(e.target.value)}
              placeholder="∞"
            />
          </label>
          <label className="prices-sort">
            <select value={sort} onChange={(e) => setSort(e.target.value as SortMode)}>
              <option value="id">{t("prices.sort_default")}</option>
              <option value="price_desc">{t("prices.sort_high")}</option>
              <option value="price_asc">{t("prices.sort_low")}</option>
            </select>
          </label>
        </div>
      </div>

      {error ? (
        <p className="error" style={{ color: "#fca5a5" }}>
          {error}
        </p>
      ) : null}

      <div className="pager">
        <button type="button" className="secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
          {t("filter.prev")}
        </button>
        <div className="center">{t("filter.page", { page, total: totalPages })}</div>
        <button
          type="button"
          className="secondary"
          disabled={page >= totalPages}
          onClick={() => setPage((p) => p + 1)}
        >
          {t("filter.next")}
        </button>
      </div>

      {!cards.length && !loading ? (
        <p className="muted">{t("filter.no_results")}</p>
      ) : (
        <div className="price-wall">
          {cards.map((c) => (
            <PriceWallTile
              key={c.id}
              card={c}
              price={prices[c.id]?.current_price}
              lastChecked={prices[c.id]?.last_checked}
              watched={isOnWatchlist(c.id, watchlist)}
              onToggleWatch={toggleWatch}
            />
          ))}
        </div>
      )}

      {cards.length > 0 ? (
        <div className="pager">
          <button type="button" className="secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            {t("filter.prev")}
          </button>
          <div className="center">{t("filter.page", { page, total: totalPages })}</div>
          <button
            type="button"
            className="secondary"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
            {t("filter.next")}
          </button>
        </div>
      ) : null}
    </div>
  );
}
