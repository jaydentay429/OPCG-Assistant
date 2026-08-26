"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type MouseEvent } from "react";
import {
  fetchTopdecksDecks,
  fetchTopdecksDetail,
  fetchTopdecksMeta,
  likeTopdeck,
  type TopdeckBrief,
  type TopdeckDetail,
  type TopdeckFacetRow,
  type TopdeckMetaRow,
  type TopdecksMetaResponse,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { localizeCardName } from "@/lib/cardLocale";
import { cardIdSortKey, displayCardId } from "@/lib/cardId";
import { copyTextToClipboard } from "@/lib/clipboard";
import { buildDeckImage, downloadDeckImage } from "@/lib/deckExport";
import { buildDeckShareUrl } from "@/lib/deckShare";
import { useI18n } from "@/lib/i18n";
import {
  displayAuthor,
  displayKeepingParens,
  pickFacetLabel,
} from "@/lib/topdeckLocale";
import { isSearchCommitKey } from "./SearchBar";
import { CardImg } from "./CardImg";

/** Group JP/EN meta pages into short set labels like OP17, OP15+EB4. */
function metaCategoryKey(slug: string): string {
  const body = String(slug || "")
    .toLowerCase()
    .replace(/^(japan|japanese|english-format|english|en-format|jp-format)-/, "");
  const parts: string[] = [];
  let rest = body;
  const re = /^(op|eb|st|prb)-?(\d+)/i;
  while (true) {
    const m = rest.match(re);
    if (!m) break;
    parts.push(`${m[1].toUpperCase()}${parseInt(m[2], 10)}`);
    rest = rest.slice(m[0].length).replace(/^-/, "");
    if (!/^(op|eb|st|prb)-?\d+/i.test(rest)) break;
  }
  return parts.length ? parts.join("+") : slug;
}

type MetaCategory = {
  key: string;
  label: string;
  slugs: string[];
  count: number;
};

type TFilterKey = "env" | "leader" | "country" | "host" | "author" | "tournament" | "placement";

type TFilters = Record<TFilterKey, string[]>;

const EMPTY_TFILTERS: TFilters = {
  env: [],
  leader: [],
  country: [],
  host: [],
  author: [],
  tournament: [],
  placement: [],
};

function toggleIn(list: string[], v: string): string[] {
  return list.includes(v) ? list.filter((x) => x !== v) : [...list, v];
}

function mainDeckCards(row: TopdeckDetail): Record<string, number> {
  const out: Record<string, number> = {};
  const leader = String(row.leader || "");
  for (const c of row.cards || []) {
    if (!c?.id || !c.qty) continue;
    if (c.is_leader || c.id === leader) continue;
    out[c.id] = c.qty;
  }
  return out;
}

function deckListText(row: TopdeckDetail): string {
  const lines: string[] = [];
  if (row.leader) lines.push(`Leader: ${displayCardId(row.leader)}`);
  const cards = mainDeckCards(row);
  for (const [id, n] of Object.entries(cards).sort((a, b) =>
    cardIdSortKey(a[0]).localeCompare(cardIdSortKey(b[0])),
  )) {
    lines.push(`${displayCardId(id)} x${n}`);
  }
  return lines.join("\n");
}

export function TournamentDecksPageClient({ hideTitle = false }: { hideTitle?: boolean } = {}) {
  const { t, lang } = useI18n();
  const { token, requestLogin } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const openDeckId = String(searchParams.get("deck") || "").trim();
  const returnTo = (() => {
    const raw = String(searchParams.get("return") || "").trim();
    // Only allow in-app relative paths
    if (!raw.startsWith("/") || raw.startsWith("//")) return "";
    return raw;
  })();
  const [meta, setMeta] = useState<TopdecksMetaResponse | null>(null);
  const [filters, setFilters] = useState<TFilters>(EMPTY_TFILTERS);
  const [openKey, setOpenKey] = useState<TFilterKey | null>(null);
  const [panelQ, setPanelQ] = useState("");
  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [items, setItems] = useState<TopdeckBrief[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [detail, setDetail] = useState<TopdeckDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [previewUrl, setPreviewUrl] = useState("");
  const [previewTitle, setPreviewTitle] = useState("");
  const [previewError, setPreviewError] = useState("");
  const [exporting, setExporting] = useState(false);
  const [actionMsg, setActionMsg] = useState("");
  const previewUrlRef = useRef("");
  const previewRunRef = useRef(0);
  const filterBarRef = useRef<HTMLDivElement | null>(null);
  const limit = 40;

  useEffect(() => {
    const tmr = setTimeout(() => setDebouncedQ(q.trim()), 220);
    return () => clearTimeout(tmr);
  }, [q]);

  useEffect(() => {
    let cancelled = false;
    fetchTopdecksMeta()
      .then((res) => {
        if (cancelled) return;
        setMeta(res);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!openKey) return;
    const onPointerDown = (e: PointerEvent) => {
      const root = filterBarRef.current;
      if (!root) return;
      if (e.target instanceof Node && root.contains(e.target)) return;
      setOpenKey(null);
      setPanelQ("");
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [openKey]);

  const categories = useMemo(() => {
    const jp = meta?.formats?.jp?.metas || [];
    const en = meta?.formats?.en?.metas || [];
    const seenSlug = new Set<string>();
    const byKey = new Map<string, MetaCategory>();
    const order: string[] = [];
    for (const row of [...jp, ...en] as TopdeckMetaRow[]) {
      if (!row?.slug || seenSlug.has(row.slug)) continue;
      seenSlug.add(row.slug);
      const key = metaCategoryKey(row.slug);
      const existing = byKey.get(key);
      if (existing) {
        existing.slugs.push(row.slug);
        existing.count += row.deck_count ?? 0;
      } else {
        byKey.set(key, {
          key,
          label: key,
          slugs: [row.slug],
          count: row.deck_count ?? 0,
        });
        order.push(key);
      }
    }
    const rank = (k: string) => {
      const m = k.match(/^(OP|EB|ST|PRB)(\d+)/);
      if (!m) return [0, 0, k] as const;
      const kind = { OP: 4, EB: 3, ST: 2, PRB: 1 }[m[1]] || 0;
      return [parseInt(m[2], 10), kind, k] as const;
    };
    return [...order]
      .sort((a, b) => {
        const ra = rank(a);
        const rb = rank(b);
        if (ra[0] !== rb[0]) return rb[0] - ra[0];
        if (ra[1] !== rb[1]) return rb[1] - ra[1];
        return String(ra[2]).localeCompare(String(rb[2]));
      })
      .map((k) => byKey.get(k)!);
  }, [meta]);

  const categoryByKey = useMemo(() => {
    const m = new Map<string, MetaCategory>();
    for (const c of categories) m.set(c.key, c);
    return m;
  }, [categories]);

  const selectedMetaSlugs = useMemo(() => {
    if (!filters.env.length) return undefined;
    const slugs = new Set<string>();
    for (const key of filters.env) {
      const cat = categoryByKey.get(key);
      if (!cat) continue;
      for (const s of cat.slugs) slugs.add(s);
    }
    return slugs.size ? Array.from(slugs).join(",") : undefined;
  }, [filters.env, categoryByKey]);

  useEffect(() => {
    if (!filters.env.length) return;
    const valid = new Set(categories.map((c) => c.key));
    const next = filters.env.filter((k) => valid.has(k));
    if (next.length !== filters.env.length) {
      setFilters((prev) => ({ ...prev, env: next }));
    }
  }, [categories, filters.env]);

  useEffect(() => {
    setOffset(0);
  }, [filters, debouncedQ]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    fetchTopdecksDecks({
      format: "all",
      meta: selectedMetaSlugs,
      leader: filters.leader.join(",") || undefined,
      country: filters.country.join(",") || undefined,
      host: filters.host.join(",") || undefined,
      author: filters.author.join(",") || undefined,
      tournament: filters.tournament.join(",") || undefined,
      placement: filters.placement.join(",") || undefined,
      q: debouncedQ || undefined,
      offset,
      limit,
      // Do not depend on token: auth hydrate used to refetch and flash a second load.
      token: undefined,
    })
      .then((res) => {
        if (cancelled) return;
        setItems(res.items || []);
        setTotal(res.total || 0);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
        setItems([]);
        setTotal(0);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedMetaSlugs, filters, debouncedQ, offset]);

  const filterGroups = useMemo(() => {
    const facetMeta = (rows: TopdeckFacetRow[] | undefined) => {
      const list = rows || [];
      const counts = new Map<string, number>();
      const labels = new Map<string, string>();
      for (const r of list) {
        counts.set(r.value, r.count);
        labels.set(r.value, pickFacetLabel(lang, r.value, null, r));
      }
      return {
        items: list.map((r) => r.value),
        counts,
        labels,
      };
    };
    const country = facetMeta(meta?.facets?.country);
    const host = facetMeta(meta?.facets?.host);
    const author = facetMeta(meta?.facets?.author);
    const tournament = facetMeta(meta?.facets?.tournament);
    const placement = facetMeta(meta?.facets?.placement);
    const leader = facetMeta(meta?.facets?.leader);
    return [
      {
        key: "env" as const,
        label: t("tournaments.dim_env"),
        items: categories.map((c) => c.key),
        counts: new Map(categories.map((c) => [c.key, c.count])),
        labels: new Map(categories.map((c) => [c.key, c.label])),
      },
      { key: "leader" as const, label: t("tournaments.dim_leader"), ...leader },
      { key: "country" as const, label: t("tournaments.dim_country"), ...country },
      { key: "host" as const, label: t("tournaments.dim_store"), ...host },
      { key: "author" as const, label: t("tournaments.dim_player"), ...author },
      { key: "tournament" as const, label: t("tournaments.dim_event"), ...tournament },
      { key: "placement" as const, label: t("tournaments.dim_place"), ...placement },
    ];
  }, [t, lang, categories, meta]);

  const activeChips = useMemo(() => {
    return filterGroups.flatMap((group) =>
      (filters[group.key] || []).map((value) => ({
        groupKey: group.key,
        label: `${group.label}: ${group.labels.get(value) || value}`,
        value,
      })),
    );
  }, [filterGroups, filters]);

  const openGroup = filterGroups.find((g) => g.key === openKey) || null;
  const openItems = useMemo(() => {
    if (!openGroup) return [];
    const needle = panelQ.trim().toLowerCase();
    if (!needle) return openGroup.items;
    return openGroup.items.filter((v) => {
      const label = (openGroup.labels.get(v) || v).toLowerCase();
      return v.toLowerCase().includes(needle) || label.includes(needle);
    });
  }, [openGroup, panelQ]);

  function tournamentMetaLine(row: TopdeckDetail): string {
    return [
      displayKeepingParens(lang, row.placement, row.placement_key, row.placement_labels),
      displayAuthor(row.author, t("tournaments.player_unknown")),
      pickFacetLabel(lang, row.country_key || row.country || "", row.country_labels),
      row.date,
      displayKeepingParens(lang, row.tournament, row.tournament_key, row.tournament_labels),
      row.host || row.host_key,
    ]
      .filter(Boolean)
      .join(" · ");
  }

  function exportPayload(row: TopdeckDetail, includeQr: boolean) {
    const cards = mainDeckCards(row);
    const cardCount = Object.values(cards).reduce((a, b) => a + b, 0) + (row.leader ? 1 : 0);
    const unique = Object.keys(cards).length + (row.leader ? 1 : 0);
    return {
      name: row.name || row.leader_name || t("deck.unnamed"),
      leader: row.leader || null,
      cards,
      lang,
      includeQr,
      subtitle: tournamentMetaLine(row),
      labels: {
        title: t("deck.unnamed"),
        leader: t("deck.leader_short"),
        noLeader: t("deck.no_leader"),
        cardsN: t("deck.export_cards_n", { count: cardCount }),
        uniqueN: t("deck.export_kinds_n", { count: unique }),
        costCurve: t("deck.export_cost"),
        powerCurve: t("deck.export_power"),
        counterCurve: t("deck.curve_counter"),
        createdBy: t("deck.export_created"),
        qty: "×",
      },
    };
  }

  async function onToggleLike(row: TopdeckBrief, event: MouseEvent) {
    event.stopPropagation();
    event.preventDefault();
    if (!token) {
      requestLogin();
      return;
    }
    const prevCount = Number(row.like_count || 0);
    const prevLiked = Boolean(row.liked_by_me);
    const nextLiked = !prevLiked;
    setItems((list) =>
      list.map((it) =>
        it.id === row.id
          ? {
              ...it,
              liked_by_me: nextLiked,
              like_count: Math.max(0, prevCount + (nextLiked ? 1 : -1)),
            }
          : it,
      ),
    );
    try {
      const res = await likeTopdeck(token, row.id, nextLiked);
      setItems((list) =>
        list.map((it) =>
          it.id === row.id
            ? { ...it, liked_by_me: res.liked_by_me, like_count: res.like_count }
            : it,
        ),
      );
    } catch {
      setItems((list) =>
        list.map((it) =>
          it.id === row.id ? { ...it, liked_by_me: prevLiked, like_count: prevCount } : it,
        ),
      );
    }
  }

  function clearPreview() {
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    previewUrlRef.current = "";
    setPreviewUrl("");
    setPreviewTitle("");
    setPreviewError("");
  }

  function closeDetail() {
    previewRunRef.current += 1;
    setDetail(null);
    setDetailLoading(false);
    setExporting(false);
    setActionMsg("");
    clearPreview();
    if (returnTo) {
      // Came from card detail: pop tournaments so the next Back goes to search,
      // not an extra stacked card entry from router.push(returnTo).
      let fromCard = false;
      try {
        fromCard = sessionStorage.getItem("opcg_tourney_return") === returnTo;
        if (fromCard) sessionStorage.removeItem("opcg_tourney_return");
      } catch {
        /* ignore */
      }
      if (fromCard) {
        router.back();
      } else {
        router.replace(returnTo);
      }
      return;
    }
    if (openDeckId) {
      router.back();
    }
  }

  async function openDetail(id: string) {
    const runId = previewRunRef.current + 1;
    previewRunRef.current = runId;
    clearPreview();
    setDetail(null);
    setDetailLoading(true);
    setExporting(true);
    setActionMsg("");
    try {
      const row = await fetchTopdecksDetail(id, token);
      if (previewRunRef.current !== runId) return;
      setDetail(row);
      setDetailLoading(false);

      try {
        const result = await buildDeckImage(exportPayload(row, false));
        if (previewRunRef.current !== runId) return;
        const url = URL.createObjectURL(result.blob);
        previewUrlRef.current = url;
        setPreviewUrl(url);
        setPreviewTitle(result.title);
        setPreviewError("");
      } catch (e) {
        if (previewRunRef.current !== runId) return;
        setPreviewError(e instanceof Error ? e.message : String(e));
      }
    } catch (e) {
      if (previewRunRef.current !== runId) return;
      setError(e instanceof Error ? e.message : String(e));
      setDetailLoading(false);
    } finally {
      if (previewRunRef.current === runId) setExporting(false);
    }
  }

  useEffect(() => {
    if (!openDeckId) return;
    void openDetail(openDeckId);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- open once per deck query
  }, [openDeckId, token]);

  async function onDownloadDeck() {
    if (!detail) return;
    setExporting(true);
    try {
      await downloadDeckImage(exportPayload(detail, true));
      setActionMsg(t("deck.export_ok"));
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : t("deck.export_fail"));
    } finally {
      setExporting(false);
    }
  }

  async function onCopyList() {
    if (!detail) return;
    const text = deckListText(detail);
    if (!text) {
      setActionMsg(t("deck.export_empty"));
      return;
    }
    if (await copyTextToClipboard(text)) {
      setActionMsg(t("deck.copy_ok"));
      return;
    }
    setActionMsg(t("deck.copy_manual"));
  }

  function importUrl(row: TopdeckDetail | TopdeckBrief, cards?: Record<string, number>, leader?: string | null) {
    const cardMap: Record<string, number> = { ...(cards || {}) };
    const leaderId = leader || row.leader || null;
    if (leaderId && cardMap[leaderId]) {
      const next = { ...cardMap };
      delete next[leaderId];
      return buildDeckShareUrl({
        name: row.name || row.leader_name || "Tournament Deck",
        leader: leaderId,
        cards: next,
      });
    }
    return buildDeckShareUrl({
      name: row.name || row.leader_name || "Tournament Deck",
      leader: leaderId,
      cards: cardMap,
    });
  }

  const totalPages = Math.max(1, Math.ceil(total / limit));
  const page = Math.floor(offset / limit) + 1;

  return (
    <div className="stack">
      {!hideTitle ? <h1 className="page-title">{t("tournaments.title")}</h1> : null}

      <form
        className="tournaments-toolbar"
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          setDebouncedQ(q.trim());
        }}
      >
        <input
          type="search"
          name="q"
          enterKeyHint="search"
          autoComplete="off"
          className="tournaments-search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (!isSearchCommitKey(e)) return;
            e.preventDefault();
            setDebouncedQ(q.trim());
            e.currentTarget.blur();
          }}
          onSearch={(e) => {
            e.preventDefault();
            setDebouncedQ(q.trim());
            e.currentTarget.blur();
          }}
          placeholder={t("tournaments.search_ph")}
          aria-label={t("tournaments.search_ph")}
        />
        <button type="submit" className="search-submit-btn">
          {t("search.submit")}
        </button>
      </form>

      <div className="filter-wrap tournaments-filter-wrap">
        <div className="filter-head-row">
          <span className="muted">{t("filter.active", { count: activeChips.length })}</span>
          <button
            type="button"
            className="ghost filter-clear-btn"
            disabled={activeChips.length === 0}
            onClick={() => setFilters(EMPTY_TFILTERS)}
          >
            {t("filter.clear")}
          </button>
        </div>

        {activeChips.length > 0 ? (
          <div className="filter-chip-row">
            {activeChips.map((chip) => (
              <button
                key={`${chip.groupKey}-${chip.value}`}
                type="button"
                className="filter-chip"
                onClick={() =>
                  setFilters((prev) => ({
                    ...prev,
                    [chip.groupKey]: prev[chip.groupKey].filter((x) => x !== chip.value),
                  }))
                }
                title={t("filter.remove")}
              >
                {chip.label} ×
              </button>
            ))}
          </div>
        ) : null}

        <div className="filter-bar" ref={filterBarRef}>
          {filterGroups.map((group) => {
            const selected = filters[group.key] || [];
            const isOpen = openKey === group.key;
            return (
              <details key={group.key} className="filter-pop" open={isOpen}>
                <summary
                  className="filter-summary"
                  onClick={(e) => {
                    e.preventDefault();
                    setOpenKey((prev) => {
                      const next = prev === group.key ? null : group.key;
                      setPanelQ("");
                      return next;
                    });
                  }}
                >
                  <span className="filter-summary-label">
                    {group.label}
                    {selected.length ? ` (${selected.length})` : ""}
                  </span>
                </summary>
                <div className="filter-panel">
                  {group.items.length > 16 ? (
                    <input
                      type="search"
                      enterKeyHint="search"
                      className="tournaments-panel-search"
                      value={isOpen ? panelQ : ""}
                      onChange={(e) => setPanelQ(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          e.currentTarget.blur();
                        }
                      }}
                      placeholder={t("tournaments.chip_filter_ph")}
                      aria-label={t("tournaments.chip_filter_ph")}
                      onClick={(e) => e.stopPropagation()}
                    />
                  ) : null}
                  {(isOpen ? openItems : group.items.slice(0, 0)).map((item) => {
                    const count = group.counts.get(item);
                    const itemLabel = group.labels.get(item) || item;
                    return (
                      <label key={item}>
                        <input
                          type="checkbox"
                          checked={selected.includes(item)}
                          onChange={() =>
                            setFilters((prev) => ({
                              ...prev,
                              [group.key]: toggleIn(prev[group.key], item),
                            }))
                          }
                        />
                        <span className="filter-item-text">
                          {itemLabel}
                          {count != null ? ` (${count})` : ""}
                        </span>
                      </label>
                    );
                  })}
                </div>
              </details>
            );
          })}
        </div>
      </div>

      <p className="muted search-result-hint">
        {t("tournaments.result", { total })}
        {loading ? ` ${t("tournaments.loading")}` : ""}
        {meta?.synced_at ? ` · ${t("tournaments.synced", { at: String(meta.synced_at).slice(0, 10) })}` : ""}
      </p>

      {error ? (
        <p className="error" style={{ color: "#fca5a5" }}>
          {error}
        </p>
      ) : null}

      <div className="pager">
        <button
          type="button"
          className="secondary"
          disabled={page <= 1}
          onClick={() => setOffset(Math.max(0, offset - limit))}
        >
          {t("filter.prev")}
        </button>
        <div className="center">{t("filter.page", { page, total: totalPages })}</div>
        <button
          type="button"
          className="secondary"
          disabled={page >= totalPages}
          onClick={() => setOffset(offset + limit)}
        >
          {t("filter.next")}
        </button>
      </div>

      {!items.length && !loading ? (
        <p className="muted">{t("tournaments.empty")}</p>
      ) : (
        <div className="tournament-table-wrap">
          <table className="tournament-table">
            <thead>
              <tr>
                <th>{t("tournaments.col_leader")}</th>
                <th>{t("tournaments.col_id")}</th>
                <th>{t("tournaments.col_date")}</th>
                <th>{t("tournaments.col_country")}</th>
                <th>{t("tournaments.col_store")}</th>
                <th>{t("tournaments.col_player")}</th>
                <th>{t("tournaments.col_event")}</th>
                <th>{t("tournaments.col_place")}</th>
                <th className="tournament-col-like">{t("tournaments.col_like")}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => {
                const leaderName =
                  localizeCardName(row.leader_name, row.leader_name_en, lang) ||
                  row.leader_name ||
                  row.leader ||
                  "—";
                return (
                  <tr key={row.id} className="tournament-row" onClick={() => void openDetail(row.id)}>
                    <td className="tournament-col-leader">
                      <span className="tournament-leader-cell">
                        <span className="tournament-leader-art">
                          {row.leader ? <CardImg cardId={row.leader} alt={leaderName} /> : null}
                        </span>
                        <span className="tournament-leader-name">{leaderName}</span>
                      </span>
                    </td>
                    <td>{displayCardId(row.leader) || "—"}</td>
                    <td>{row.date || "—"}</td>
                    <td>{pickFacetLabel(lang, row.country_key || row.country || "", row.country_labels) || "—"}</td>
                    <td>{row.host || "—"}</td>
                    <td>{displayAuthor(row.author, t("tournaments.player_unknown")) || "—"}</td>
                    <td>
                      {displayKeepingParens(lang, row.tournament, row.tournament_key, row.tournament_labels) ||
                        "—"}
                    </td>
                    <td>
                      {displayKeepingParens(lang, row.placement, row.placement_key, row.placement_labels) || "—"}
                    </td>
                    <td className="tournament-col-like">
                      <button
                        type="button"
                        className={`tournament-like-btn${row.liked_by_me ? " is-liked" : ""}`}
                        aria-label={row.liked_by_me ? t("tournaments.unlike") : t("tournaments.like")}
                        aria-pressed={Boolean(row.liked_by_me)}
                        onClick={(e) => void onToggleLike(row, e)}
                      >
                        <span aria-hidden="true">{row.liked_by_me ? "♥" : "♡"}</span>
                        <span>{Number(row.like_count || 0)}</span>
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <p className="muted tournaments-attr">
        {t("tournaments.attribution")}{" "}
        <a href={meta?.source || "https://onepiecetopdecks.com/deck-list/"} target="_blank" rel="noreferrer">
          {meta?.attribution || "ONE PIECE TOP DECKS"}
        </a>
      </p>

      {(detail || detailLoading) && (
        <div
          className="deck-details-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeDetail();
          }}
        >
          <section
            className="deck-details-modal tournament-details-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="tournament-details-title"
          >
            <div className="deck-details-head">
              <div className="tournament-details-title-wrap">
                <h2 id="tournament-details-title">
                  {detail?.name || detail?.leader_name || t("deck.details")}
                </h2>
              </div>
              <button type="button" className="ghost" onClick={closeDetail} aria-label={t("tournaments.close")}>
                ×
              </button>
            </div>

            <div className="tournament-details-body">
              {detail ? (
                <div className="tournament-details-actions">
                  <Link
                    className="tournament-action-btn tournament-action-btn-primary"
                    href={importUrl(detail, mainDeckCards(detail), detail.leader)}
                  >
                    {t("tournaments.import")}
                  </Link>
                  <button
                    type="button"
                    className="tournament-action-btn tournament-action-btn-secondary"
                    onClick={() => void onCopyList()}
                  >
                    {t("deck.copy_list")}
                  </button>
                  <button
                    type="button"
                    className="tournament-action-btn tournament-action-btn-primary"
                    onClick={() => void onDownloadDeck()}
                    disabled={exporting}
                  >
                    {exporting ? t("deck.exporting") : t("deck.download_image")}
                  </button>
                </div>
              ) : null}

              <div className="deck-details-preview tournament-preview">
                {previewUrl ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={previewUrl} alt={previewTitle || t("deck.details")} />
                ) : detail && !detailLoading && !exporting ? (
                  <div className="tournament-preview-fallback">
                    {detail.leader ? (
                      <div className="tournament-preview-leader">
                        <CardImg cardId={detail.leader} alt={detail.leader_name || detail.leader} loading="eager" />
                      </div>
                    ) : null}
                    <div className="tournament-preview-grid">
                      {(detail.cards || [])
                        .filter((c) => c?.id && !c.is_leader && c.id !== detail.leader)
                        .slice(0, 30)
                        .map((c) => (
                          <div key={c.id} className="tournament-preview-tile" title={`${c.id}×${c.qty}`}>
                            <CardImg cardId={c.id} alt={c.id} />
                            <span>×{c.qty}</span>
                          </div>
                        ))}
                    </div>
                    {previewError ? (
                      <p className="muted tournament-preview-fallback-note">{t("deck.export_fail")}</p>
                    ) : null}
                  </div>
                ) : (
                  <div className="deck-details-loading">
                    {detailLoading || exporting ? t("deck.exporting") : t("tournaments.loading")}
                  </div>
                )}
              </div>
            </div>

            {actionMsg ? <p className="muted tournament-action-msg">{actionMsg}</p> : null}
          </section>
        </div>
      )}
    </div>
  );
}
