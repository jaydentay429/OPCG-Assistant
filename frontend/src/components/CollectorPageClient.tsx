"use client";

import Link from "next/link";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  cardImageUrl,
  collectionAdd,
  collectionRemove,
  fetchCollection,
  fetchDeckStatsBatch,
  type BatchPriceFields,
  type DeckStatFields,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cardIdSortKey, displayCardId } from "@/lib/cardId";
import { cardMatchesCollectionQuery } from "@/lib/cardSearchMatch";
import { useI18n } from "@/lib/i18n";
import { formatYen, loadUnitPrices, sumPricedCopies, unitPriceOf } from "@/lib/priceCalc";
import { consumeSkipScrollRestore, flushCurrentScroll, readPathScrollTarget, requestScrollRestore, scrollYForPersist } from "@/lib/scrollRestore";
import type { CollectionResponse } from "@/lib/types";
import { LoginGate } from "./LoginGate";
import { SearchPageClient } from "./SearchPageClient";

const COLLECTOR_PREFS_KEY = "opcg_collector_prefs_v1";
type CollectorSort =
  | "id_asc"
  | "id_desc"
  | "qty_desc"
  | "qty_asc"
  | "rarity_desc"
  | "rarity_asc";

type CardSearchMeta = {
  rarity: string;
  searchBlob: string;
};

function isCollectorSort(v: unknown): v is CollectorSort {
  return (
    v === "id_asc" ||
    v === "id_desc" ||
    v === "qty_desc" ||
    v === "qty_asc" ||
    v === "rarity_desc" ||
    v === "rarity_asc"
  );
}

export function CollectorPageClient() {
  const { t } = useI18n();
  const { token, isLoggedIn, ready } = useAuth();
  const [data, setData] = useState<CollectionResponse | null>(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [sortBy, setSortBy] = useState<CollectorSort>("id_asc");
  const [visibleCount, setVisibleCount] = useState(120);
  const [metaById, setMetaById] = useState<Record<string, CardSearchMeta>>({});
  const [prefsReady, setPrefsReady] = useState(false);
  const [showPrices, setShowPrices] = useState(false);
  const [priceMap, setPriceMap] = useState<Record<string, BatchPriceFields>>({});
  const [pricesLoading, setPricesLoading] = useState(false);
  const [sectionAddOpen, setSectionAddOpen] = useState(true);
  const pendingRestoreYRef = useRef(0);
  const pendingAnchorRef = useRef("");
  const restoreOnceRef = useRef(false);

  const reload = useCallback(async () => {
    if (!token) return;
    const res = await fetchCollection(token);
    setData(res);
  }, [token]);

  useEffect(() => {
    if (!ready) return;
    if (!isLoggedIn || !token) {
      setData(null);
      return;
    }
    reload().catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [ready, isLoggedIn, token, reload]);

  useLayoutEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const raw = window.localStorage.getItem(COLLECTOR_PREFS_KEY);
      if (raw) {
        const saved = JSON.parse(raw) as {
          q?: unknown;
          s?: unknown;
          v?: unknown;
          y?: unknown;
          add?: unknown;
          anchor?: unknown;
        };
        if (typeof saved.q === "string") setQuery(saved.q);
        if (isCollectorSort(saved.s)) setSortBy(saved.s);
        if (typeof saved.v === "number" && Number.isFinite(saved.v)) {
          setVisibleCount(Math.max(120, Math.floor(saved.v)));
        }
        if (typeof saved.add === "boolean") setSectionAddOpen(saved.add);
        if (!consumeSkipScrollRestore()) {
          const target = readPathScrollTarget("/collector");
          pendingRestoreYRef.current = target.y || (typeof saved.y === "number" && saved.y > 0 ? Math.floor(saved.y) : 0);
          pendingAnchorRef.current =
            target.anchor || (typeof saved.anchor === "string" ? saved.anchor : "") || "";
        } else {
          pendingRestoreYRef.current = 0;
          pendingAnchorRef.current = "";
          restoreOnceRef.current = true; // tab switch: do not restore later
        }
      } else if (consumeSkipScrollRestore()) {
        pendingRestoreYRef.current = 0;
        pendingAnchorRef.current = "";
        restoreOnceRef.current = true;
      }
    } catch {
      /* ignore invalid prefs */
    } finally {
      setPrefsReady(true);
    }
  }, []);

  useEffect(() => {
    if (!prefsReady || typeof window === "undefined") return;
    const savePrefs = (scrollY: number, anchor?: string) => {
      try {
        if (anchor) pendingAnchorRef.current = anchor;
        window.localStorage.setItem(
          COLLECTOR_PREFS_KEY,
          JSON.stringify({
            q: query,
            s: sortBy,
            v: visibleCount,
            add: sectionAddOpen,
            y: scrollYForPersist(pendingRestoreYRef.current, scrollY),
            anchor: pendingAnchorRef.current || "",
          }),
        );
      } catch {
        /* ignore storage failures */
      }
    };

    savePrefs(window.scrollY || 0);
    const onScroll = () => savePrefs(window.scrollY || 0);
    const flush = (e?: Event) => {
      const detail = (e as CustomEvent<{ y?: number; anchor?: string }> | undefined)?.detail;
      savePrefs(
        typeof detail?.y === "number" ? detail.y : window.scrollY || 0,
        typeof detail?.anchor === "string" ? detail.anchor : undefined,
      );
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
  }, [prefsReady, query, sortBy, visibleCount, sectionAddOpen]);

  async function change(id: string, delta: 1 | -1) {
    if (!token) return;
    try {
      const res =
        delta > 0 ? await collectionAdd(token, id, 1) : await collectionRemove(token, id, 1);
      setData(res);
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
  }

  const allEntries = useMemo(
    () =>
      Object.entries(data?.cards || {})
        .filter(([, n]) => Number(n) > 0)
        .map(([id, cnt]) => [id, Number(cnt) || 0] as const),
    [data?.cards],
  );

  useEffect(() => {
    const ids = allEntries.map(([id]) => id);
    const missing = ids.filter((id) => !(id in metaById));
    if (!missing.length) return;
    let cancelled = false;

    async function loadMissingMeta() {
      const next: Record<string, CardSearchMeta> = {};
      const chunkSize = 400; // backend limit is 420
      for (let i = 0; i < missing.length; i += chunkSize) {
        const chunk = missing.slice(i, i + chunkSize);
        const batch = await fetchDeckStatsBatch(chunk);
        for (const id of chunk) {
          const fields = (batch[id] || {}) as DeckStatFields;
          next[id] = {
            rarity: String(fields.rarity || "").trim().toUpperCase(),
            searchBlob: String(fields.search_blob || ""),
          };
        }
      }
      if (!cancelled && Object.keys(next).length) {
        setMetaById((prev) => ({ ...prev, ...next }));
      }
    }

    loadMissingMeta().catch(() => {
      /* ignore meta fetch failures */
    });
    return () => {
      cancelled = true;
    };
  }, [allEntries, metaById]);

  const filteredSorted = useMemo(() => {
    const rarityRank = (id: string) => {
      const r = String(metaById[id]?.rarity || "").toUpperCase();
      // Lower value means lower rarity in ascending mode.
      // Match filter category order: L-SP-TR-SEC-SR-R-UR-UC-C-P-GOLD DON-DON
      const order = ["L", "SP", "TR", "SEC", "SR", "R", "UR", "UC", "C", "P", "GOLD DON", "DON"];
      const idx = order.indexOf(r);
      if (idx >= 0) return idx;
      if (!r) return -1;
      return 100 + r.charCodeAt(0);
    };
    const q = query.trim();
    const filtered = q
      ? allEntries.filter(([id]) => {
          // Keep cards until meta loads so name search doesn't flash empty.
          if (!(id in metaById)) return true;
          return cardMatchesCollectionQuery(id, metaById[id]?.searchBlob, q);
        })
      : allEntries;
    const sorted = [...filtered];
    if (sortBy === "qty_desc") {
      sorted.sort((a, b) => b[1] - a[1] || cardIdSortKey(a[0]).localeCompare(cardIdSortKey(b[0])));
    } else if (sortBy === "qty_asc") {
      sorted.sort((a, b) => a[1] - b[1] || cardIdSortKey(a[0]).localeCompare(cardIdSortKey(b[0])));
    } else if (sortBy === "id_desc") {
      sorted.sort((a, b) => cardIdSortKey(b[0]).localeCompare(cardIdSortKey(a[0])));
    } else if (sortBy === "rarity_desc") {
      sorted.sort(
        (a, b) => rarityRank(b[0]) - rarityRank(a[0]) || cardIdSortKey(a[0]).localeCompare(cardIdSortKey(b[0])),
      );
    } else if (sortBy === "rarity_asc") {
      sorted.sort(
        (a, b) => rarityRank(a[0]) - rarityRank(b[0]) || cardIdSortKey(a[0]).localeCompare(cardIdSortKey(b[0])),
      );
    } else {
      sorted.sort((a, b) => cardIdSortKey(a[0]).localeCompare(cardIdSortKey(b[0])));
    }
    return sorted;
  }, [allEntries, query, metaById, sortBy]);

  useEffect(() => {
    setVisibleCount(120);
  }, [query, sortBy]);

  const entries = filteredSorted.slice(0, visibleCount);
  const hasMore = entries.length < filteredSorted.length;

  useLayoutEffect(() => {
    if (!prefsReady || data == null) return;
    if (restoreOnceRef.current) return;
    if (!pendingRestoreYRef.current && !pendingAnchorRef.current) return;
    restoreOnceRef.current = true;
    const y = pendingRestoreYRef.current;
    const anchor = pendingAnchorRef.current;
    requestScrollRestore({ y, anchor }, () => {
      pendingRestoreYRef.current = 0;
      pendingAnchorRef.current = "";
    });
  }, [prefsReady, data, sectionAddOpen]);

  const collectionPriceIdsKey = useMemo(
    () =>
      Object.keys(data?.cards || {})
        .filter((id) => Number((data?.cards || {})[id]) > 0)
        .sort()
        .join("|"),
    [data?.cards],
  );

  useEffect(() => {
    if (!showPrices) return;
    const ids = collectionPriceIdsKey ? collectionPriceIdsKey.split("|").filter(Boolean) : [];
    if (!ids.length) {
      setPriceMap({});
      return;
    }
    let cancelled = false;
    setPricesLoading(true);
    loadUnitPrices(ids)
      .then((map) => {
        if (!cancelled) setPriceMap(map);
      })
      .catch(() => {
        if (!cancelled) setPriceMap({});
      })
      .finally(() => {
        if (!cancelled) setPricesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [showPrices, collectionPriceIdsKey]);

  const collectionPriceSummary = useMemo(() => {
    if (!showPrices) return null;
    // Total for the filtered view the user is looking at.
    const cards = Object.fromEntries(filteredSorted);
    return sumPricedCopies(cards, priceMap);
  }, [showPrices, filteredSorted, priceMap]);

  return (
    <div className="stack">
      <h1 className="page-title">{t("page.collector")}</h1>
      {!ready ? (
        <p className="muted">…</p>
      ) : !isLoggedIn ? (
        <LoginGate title={t("collector.login_title")} body={t("collector.login_body")} />
      ) : (
        <>
          {error ? <p style={{ color: "#fca5a5" }}>{error}</p> : null}
          <section className="deck-panel">
            <div className="collector-stats-grid">
              <div className="collector-stat-card">
                <span className="muted">{t("collector.unique")}</span>
                <strong>{data?.total_unique || 0}</strong>
              </div>
              <div className="collector-stat-card">
                <span className="muted">{t("collector.copies")}</span>
                <strong>{data?.total_copies || 0}</strong>
              </div>
              <div className="collector-stat-card full">
                <span className="muted">
                  {t("collector.showing", { shown: entries.length, total: filteredSorted.length })}
                </span>
              </div>
              {showPrices ? (
                <div className="collector-stat-card full price-total-card">
                  <span className="muted">{t("price.total_label")}</span>
                  <strong>
                    {pricesLoading
                      ? t("price.loading")
                      : formatYen(collectionPriceSummary?.total ?? 0)}
                  </strong>
                  {!pricesLoading && (collectionPriceSummary?.missingCopies || 0) > 0 ? (
                    <span className="muted">
                      {t("price.missing_note", {
                        missing: String(collectionPriceSummary?.missingCopies ?? 0),
                      })}
                    </span>
                  ) : null}
                </div>
              ) : null}
            </div>

            <div className="collector-tools">
              <input
                type="search"
                enterKeyHint="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key !== "Enter") return;
                  if (e.nativeEvent.isComposing || e.keyCode === 229) return;
                  e.preventDefault();
                  e.currentTarget.blur();
                }}
                onSearch={(e) => {
                  e.preventDefault();
                  e.currentTarget.blur();
                }}
                placeholder={t("collector.search_ph")}
                className="collector-search"
                aria-label={t("collector.search_ph")}
              />
              <select
                className="collector-sort"
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
              >
                <option value="id_asc">{t("collector.sort_id_asc")}</option>
                <option value="id_desc">{t("collector.sort_id_desc")}</option>
                <option value="qty_desc">{t("collector.sort_qty_desc")}</option>
                <option value="qty_asc">{t("collector.sort_qty_asc")}</option>
                <option value="rarity_desc">{t("collector.sort_rarity_desc")}</option>
                <option value="rarity_asc">{t("collector.sort_rarity_asc")}</option>
              </select>
              <button
                type="button"
                className={`btn-price${showPrices ? " active" : ""}`}
                onClick={() => setShowPrices((v) => !v)}
                disabled={!Object.keys(data?.cards || {}).length}
              >
                {showPrices ? t("price.hide") : t("price.show")}
              </button>
            </div>

            {!entries.length ? (
              <p className="muted collector-empty">{t("collector.empty")}</p>
            ) : (
              <div className="collector-grid">
                {entries.map(([id, cnt]) => {
                  const unit = unitPriceOf(priceMap, id);
                  const line = unit == null ? null : unit * Number(cnt);
                  return (
                    <article key={id} className="collector-card" data-scroll-anchor={id}>
                      <Link
                        href={`/cards/${encodeURIComponent(id)}?pickedVariant=${encodeURIComponent(id)}`}
                        className="collector-art"
                        scroll={false}
                        onPointerDown={() => flushCurrentScroll(id)}
                        onClick={() => flushCurrentScroll(id)}
                      >
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={cardImageUrl(id)} alt={id} />
                      </Link>
                      <div className="collector-meta">
                        <div className="collector-meta-row">
                          <strong>{displayCardId(id)}</strong>
                          <span className="count">
                            {metaById[id]?.rarity ? `${metaById[id].rarity} · ` : ""}×{cnt}
                          </span>
                        </div>
                        {showPrices ? (
                          <span
                            className="price-chip"
                            title={unit != null ? `${formatYen(unit)} × ${cnt}` : undefined}
                          >
                            {formatYen(line)}
                          </span>
                        ) : null}
                      </div>
                      <div className="collector-actions">
                        <button type="button" className="btn-remove" onClick={() => change(id, -1)}>
                          -1
                        </button>
                        <button type="button" className="btn-add" onClick={() => change(id, 1)}>
                          +1
                        </button>
                      </div>
                    </article>
                  );
                })}
              </div>
            )}

            {hasMore ? (
              <div className="collector-more-wrap">
                <button type="button" className="secondary" onClick={() => setVisibleCount((v) => v + 120)}>
                  {t("collector.show_more")}
                </button>
              </div>
            ) : null}
          </section>
          <p className="muted collector-tip">{t("collector.stats", { unique: data?.total_unique || 0, copies: data?.total_copies || 0 })}</p>
        </>
      )}
      <section className="deck-panel deck-search-wrap">
        <div className="deck-section-head">
          <div>
            <h2 className="deck-section-title">{t("collector.add_cards_title")}</h2>
            <p className="muted deck-section-sub">{t("collector.add_cards_sub")}</p>
          </div>
          <button type="button" className="secondary" onClick={() => setSectionAddOpen((v) => !v)}>
            {sectionAddOpen ? t("deck.section_collapse") : t("deck.section_expand")}
          </button>
        </div>
        {sectionAddOpen ? <SearchPageClient hideHeader /> : null}
      </section>
    </div>
  );
}
