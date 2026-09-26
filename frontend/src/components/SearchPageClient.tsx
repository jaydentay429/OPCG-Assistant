"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { fetchFilterCards, fetchFilterOptions } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import {
  consumeSkipScrollRestore,
  readPathScrollTarget,
  requestScrollRestore,
  scrollYForPersist,
} from "@/lib/scrollRestore";
import type { FilterCard, FilterOptions, FilterState } from "@/lib/types";
import { CardWall, CardWallSkeleton } from "./CardWall";
import { EMPTY_FILTERS, FilterBar } from "./FilterBar";
import { SearchBar } from "./SearchBar";

const PAGE_SIZE = 70;
const STORAGE_KEY = "opcg_search_state_v1";
const EMBED_STORAGE_KEY = "opcg_embed_search_v1";

type SavedSearchState = {
  q: string;
  filters: FilterState;
  page: number;
  y?: number;
  anchor?: string;
};

function loadSavedSearch(key: string): SavedSearchState {
  if (typeof window === "undefined") {
    return { q: "", filters: EMPTY_FILTERS, page: 1, y: 0, anchor: "" };
  }
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return { q: "", filters: EMPTY_FILTERS, page: 1, y: 0, anchor: "" };
    const parsed = JSON.parse(raw) as Partial<SavedSearchState>;
    return {
      q: typeof parsed.q === "string" ? parsed.q : "",
      filters: { ...EMPTY_FILTERS, ...(parsed.filters || {}) },
      page: Number.isFinite(Number(parsed.page)) && Number(parsed.page) >= 1 ? Math.floor(Number(parsed.page)) : 1,
      y: Number.isFinite(Number(parsed.y)) && Number(parsed.y) > 0 ? Math.floor(Number(parsed.y)) : 0,
      anchor: typeof parsed.anchor === "string" ? parsed.anchor : "",
    };
  } catch {
    return { q: "", filters: EMPTY_FILTERS, page: 1, y: 0, anchor: "" };
  }
}

function filtersToQuery(f: FilterState, q: string, page: number) {
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
    offset: (page - 1) * PAGE_SIZE,
    limit: PAGE_SIZE,
  };
}

export function SearchPageClient({
  hideHeader = false,
  intro = null,
  initialQ = "",
}: {
  hideHeader?: boolean;
  intro?: ReactNode;
  initialQ?: string;
} = {}) {
  const { t } = useI18n();
  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [searchTick, setSearchTick] = useState(0);
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS);
  const [options, setOptions] = useState<FilterOptions | null>(null);
  const [cards, setCards] = useState<FilterCard[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [fetchedOnce, setFetchedOnce] = useState(false);
  const [error, setError] = useState("");
  const [restored, setRestored] = useState(false);
  const storageKey = hideHeader ? EMBED_STORAGE_KEY : STORAGE_KEY;
  const skipPageResetRef = useRef(false);
  const pendingRestoreYRef = useRef(0);
  const pendingAnchorRef = useRef("");
  const restoreOnceRef = useRef(false);

  useLayoutEffect(() => {
    const saved = loadSavedSearch(storageKey);
    const pathTarget = readPathScrollTarget("/");
    const q0 = !hideHeader && initialQ.trim() ? initialQ.trim() : saved.q;
    setQ(q0);
    setDebouncedQ(q0);
    setFilters(saved.filters);
    setPage(saved.page);
    restoreOnceRef.current = false;
    // Nested search (builder/collector) must not move the window; tab switches skip restore.
    if (!hideHeader && !consumeSkipScrollRestore()) {
      pendingRestoreYRef.current = pathTarget.y || saved.y || 0;
      pendingAnchorRef.current = pathTarget.anchor || saved.anchor || "";
    } else {
      pendingRestoreYRef.current = 0;
      pendingAnchorRef.current = "";
      if (!hideHeader) restoreOnceRef.current = true;
    }
    skipPageResetRef.current = true;
    setRestored(true);
  }, [hideHeader, storageKey, initialQ]);

  const persistSearchState = (scrollY?: number) => {
    try {
      const prev = loadSavedSearch(storageKey);
      const payload: SavedSearchState = {
        q: debouncedQ,
        filters,
        page,
        y: hideHeader
          ? 0
          : scrollYForPersist(
              pendingRestoreYRef.current,
              scrollY ?? (typeof window !== "undefined" ? window.scrollY || 0 : 0),
            ),
        anchor: hideHeader ? "" : pendingAnchorRef.current || prev.anchor || "",
      };
      sessionStorage.setItem(storageKey, JSON.stringify(payload));
    } catch {
      /* ignore quota / private mode */
    }
  };

  useEffect(() => {
    if (!restored) return;
    const tmr = setTimeout(() => setDebouncedQ(q), 220);
    return () => clearTimeout(tmr);
  }, [q, restored]);

  useEffect(() => {
    fetchFilterOptions()
      .then(setOptions)
      .catch(() => setOptions({ series: [], rarities: [], blocks: [] }));
  }, []);

  useEffect(() => {
    if (!restored) return;
    if (skipPageResetRef.current) {
      skipPageResetRef.current = false;
      return;
    }
    setPage(1);
  }, [debouncedQ, filters, restored]);

  // Persist search/filter/page (and scroll on the main search page) for detail/back.
  useEffect(() => {
    if (!restored) return;
    persistSearchState();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- persist latest fields only
  }, [debouncedQ, filters, page, restored, hideHeader]);

  useEffect(() => {
    if (!restored || hideHeader) return;
    const onScroll = () => persistSearchState(window.scrollY || 0);
    const flush = (e?: Event) => {
      const detail = (e as CustomEvent<{ y?: number; anchor?: string }> | undefined)?.detail;
      if (typeof detail?.anchor === "string" && detail.anchor) {
        pendingAnchorRef.current = detail.anchor;
      }
      persistSearchState(typeof detail?.y === "number" ? detail.y : window.scrollY || 0);
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
    // eslint-disable-next-line react-hooks/exhaustive-deps -- persistence handler uses latest closure
  }, [debouncedQ, filters, page, restored, hideHeader]);

  useEffect(() => {
    if (!restored) return;
    let cancelled = false;
    const ac = new AbortController();
    setLoading(true);
    setError("");
    const query = filtersToQuery(filters, debouncedQ, page);
    fetchFilterCards(query, { signal: ac.signal })
      .then((res) => {
        if (cancelled) return;
        setCards(res.cards);
        setTotal(res.total);
        setFetchedOnce(true);
      })
      .catch((e) => {
        if (cancelled) return;
        // Ignore aborts from superseded searches.
        if (e instanceof Error && /abort|408|超时/i.test(e.message)) return;
        setError(e instanceof Error ? e.message : String(e));
        setCards([]);
        setTotal(0);
        setFetchedOnce(true);
        setLoading(false);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
      ac.abort();
    };
  }, [filters, debouncedQ, page, restored, searchTick]);

  // Restore once after the wall has data — prefer the clicked card anchor.
  useLayoutEffect(() => {
    if (hideHeader || !restored || loading) return;
    if (restoreOnceRef.current) return;
    if (!pendingRestoreYRef.current && !pendingAnchorRef.current) return;
    restoreOnceRef.current = true;
    const y = pendingRestoreYRef.current;
    const anchor = pendingAnchorRef.current;
    requestScrollRestore({ y, anchor }, () => {
      pendingRestoreYRef.current = 0;
      pendingAnchorRef.current = "";
    });
  }, [loading, cards.length, hideHeader, restored, page]);

  const totalPages = useMemo(() => Math.max(1, Math.ceil(total / PAGE_SIZE)), [total]);

  return (
    <div className="stack">
      {!hideHeader ? (
        <>
          <h1 className="page-title">{t("landing.title")}</h1>
          {/* Site blurb is in HomeSeoIntro (seo-only). */}
        </>
      ) : null}
      {!hideHeader && intro ? intro : null}
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

      <p className="muted search-result-hint">
        {!fetchedOnce
          ? t("filter.loading")
          : t("filter.filter_result", { total, size: PAGE_SIZE })}
        {fetchedOnce && loading ? " …" : ""}
      </p>

      {error ? (
        <p className="error" style={{ color: "#fca5a5" }}>
          {error}
        </p>
      ) : null}

      {fetchedOnce && totalPages > 1 ? (
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

      {loading && !cards.length ? <CardWallSkeleton /> : <CardWall cards={cards} />}

      {fetchedOnce && totalPages > 1 ? (
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
