"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  binderAutofillPage,
  binderClearPage,
  binderCreateShare,
  binderSetPageTitle,
  binderSetSlot,
  binderSwap,
  fetchBinder,
  fetchCollection,
  fetchDeckStatsBatch,
  prefetchCardImages,
  type DeckStatFields,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cardIdSortKey, displayCardId } from "@/lib/cardId";
import { cardMatchesCollectionQuery } from "@/lib/cardSearchMatch";
import { copyTextToClipboard } from "@/lib/clipboard";
import { downloadDataUrl, exportBinderPageImage } from "@/lib/binderExport";
import { useI18n } from "@/lib/i18n";
import type { BinderResponse, CollectionResponse } from "@/lib/types";
import { CardImg } from "./CardImg";
import { LoginGate } from "./LoginGate";

type DragPayload =
  | { source: "slot"; slot: number; cardId: string }
  | { source: "library"; cardId: string };

type CollSort = "id_asc" | "id_desc" | "qty_desc" | "qty_asc" | "rarity_desc" | "rarity_asc";

type CardSearchMeta = {
  rarity: string;
  searchBlob: string;
};

const DRAG_MIME = "application/x-opcg-binder";

/** Frontend slots are 0..17; backend API expects 1..18. */
function toApiSlot(slotIndex: number) {
  return slotIndex + 1;
}

function rarityRank(rarity: string) {
  const r = String(rarity || "").toUpperCase();
  // Match filter category order: L-SP-TR-SEC-SR-R-UR-UC-C-P-GOLD DON-DON
  const order = ["L", "SP", "TR", "SEC", "SR", "R", "UR", "UC", "C", "P", "GOLD DON", "DON"];
  const idx = order.indexOf(r);
  if (idx >= 0) return idx;
  if (!r) return -1;
  return 100 + r.charCodeAt(0);
}

export function BinderPageClient() {
  const { t } = useI18n();
  const { token, isLoggedIn, ready } = useAuth();
  const [binder, setBinder] = useState<BinderResponse | null>(null);
  const [collection, setCollection] = useState<CollectionResponse | null>(null);
  const [page, setPage] = useState(1);
  const [title, setTitle] = useState("");
  const [dragPayload, setDragPayload] = useState<DragPayload | null>(null);
  const dragRef = useRef<DragPayload | null>(null);
  const [pick, setPick] = useState<DragPayload | null>(null);
  const [trashHot, setTrashHot] = useState(false);
  const [msg, setMsg] = useState("");
  const [collQuery, setCollQuery] = useState("");
  const [collSort, setCollSort] = useState<CollSort>("id_asc");
  const [collVisible, setCollVisible] = useState(120);
  const [metaById, setMetaById] = useState<Record<string, CardSearchMeta>>({});
  const [shareOpen, setShareOpen] = useState(false);
  const [shareUrl, setShareUrl] = useState("");
  const [sharePhoto, setSharePhoto] = useState("");
  const [shareBusy, setShareBusy] = useState(false);

  const reload = useCallback(async () => {
    if (!token) return;
    const [b, c] = await Promise.all([fetchBinder(token), fetchCollection(token)]);
    setBinder(b);
    setCollection(c);
  }, [token]);

  useEffect(() => {
    if (!ready || !isLoggedIn || !token) {
      setBinder(null);
      setCollection(null);
      return;
    }
    reload().catch((e) => setMsg(e instanceof Error ? e.message : String(e)));
  }, [ready, isLoggedIn, token, reload]);

  useEffect(() => {
    if (!binder?.pages) return;
    const ids: string[] = [];
    for (const pageSlots of binder.pages) {
      for (const cid of pageSlots || []) {
        if (cid) ids.push(cid);
      }
    }
    prefetchCardImages(ids);
  }, [binder]);

  useEffect(() => {
    const existing = binder?.page_titles?.[page - 1] || "";
    setTitle(existing);
  }, [binder, page]);

  async function openShare() {
    if (!token || shareBusy) return;
    setShareBusy(true);
    setMsg("");
    try {
      const res = await binderCreateShare(token);
      const url = `${window.location.origin}${res.url_path}`;
      setShareUrl(url);
      const pageSlots = Array.from({ length: 18 }, (_, i) => (binder?.pages?.[page - 1] || [])[i] || null);
      prefetchCardImages(pageSlots);
      const photo = await exportBinderPageImage({
        page,
        title: (binder?.page_titles?.[page - 1] || "").trim(),
        ownerName: res.owner_name || undefined,
        slots: pageSlots,
      });
      setSharePhoto(photo);
      setShareOpen(true);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setShareBusy(false);
    }
  }

  async function copyShareLink() {
    if (!shareUrl) return;
    if (await copyTextToClipboard(shareUrl)) {
      setMsg(t("binder.share_copied"));
    }
  }

  function downloadSharePhoto() {
    if (!sharePhoto) return;
    downloadDataUrl(sharePhoto, `binder-page-${page}.png`);
  }

  const slots = useMemo(() => {
    const row = binder?.pages?.[page - 1];
    return Array.from({ length: 18 }, (_, i) => (row && row[i]) || null);
  }, [binder, page]);

  const collEntries = useMemo(
    () =>
      Object.entries(collection?.cards || {})
        .filter(([, n]) => Number(n) > 0)
        .map(([id, cnt]) => [id, Number(cnt) || 0] as const),
    [collection],
  );

  useEffect(() => {
    const ids = collEntries.map(([id]) => id);
    const missing = ids.filter((id) => !(id in metaById));
    if (!missing.length) return;
    let cancelled = false;

    async function loadMissingMeta() {
      const next: Record<string, CardSearchMeta> = {};
      const chunkSize = 400;
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
  }, [collEntries, metaById]);

  const filteredCollEntries = useMemo(() => {
    const q = collQuery.trim();
    const filtered = q
      ? collEntries.filter(([id]) => {
          if (!(id in metaById)) return true;
          return cardMatchesCollectionQuery(id, metaById[id]?.searchBlob, q);
        })
      : collEntries;
    const sorted = [...filtered];
    if (collSort === "qty_desc") {
      sorted.sort((a, b) => b[1] - a[1] || cardIdSortKey(a[0]).localeCompare(cardIdSortKey(b[0])));
    } else if (collSort === "qty_asc") {
      sorted.sort((a, b) => a[1] - b[1] || cardIdSortKey(a[0]).localeCompare(cardIdSortKey(b[0])));
    } else if (collSort === "id_desc") {
      sorted.sort((a, b) => cardIdSortKey(b[0]).localeCompare(cardIdSortKey(a[0])));
    } else if (collSort === "rarity_desc") {
      sorted.sort(
        (a, b) =>
          rarityRank(metaById[b[0]]?.rarity || "") - rarityRank(metaById[a[0]]?.rarity || "") ||
          cardIdSortKey(a[0]).localeCompare(cardIdSortKey(b[0])),
      );
    } else if (collSort === "rarity_asc") {
      sorted.sort(
        (a, b) =>
          rarityRank(metaById[a[0]]?.rarity || "") - rarityRank(metaById[b[0]]?.rarity || "") ||
          cardIdSortKey(a[0]).localeCompare(cardIdSortKey(b[0])),
      );
    } else {
      sorted.sort((a, b) => cardIdSortKey(a[0]).localeCompare(cardIdSortKey(b[0])));
    }
    return sorted;
  }, [collEntries, collQuery, collSort, metaById]);

  useEffect(() => {
    setCollVisible(120);
  }, [collQuery, collSort]);

  const shownCollEntries = filteredCollEntries.slice(0, collVisible);
  const hasMoreColl = shownCollEntries.length < filteredCollEntries.length;
  const filledSlots = useMemo(() => slots.filter(Boolean).length, [slots]);

  function beginDrag(payload: DragPayload, e: React.DragEvent) {
    dragRef.current = payload;
    setDragPayload(payload);
    try {
      e.dataTransfer.setData(DRAG_MIME, JSON.stringify(payload));
      e.dataTransfer.setData("text/plain", payload.cardId);
      e.dataTransfer.effectAllowed = "move";
    } catch {
      /* some browsers reject custom mime types */
    }
  }

  function clearDrag() {
    dragRef.current = null;
    setDragPayload(null);
    setTrashHot(false);
  }

  function readDrag(e: React.DragEvent): DragPayload | null {
    const raw = e.dataTransfer.getData(DRAG_MIME);
    if (raw) {
      try {
        return JSON.parse(raw) as DragPayload;
      } catch {
        /* fall through */
      }
    }
    return dragRef.current;
  }

  async function applyPickToSlot(toSlot: number) {
    if (!token || !pick?.cardId) return;
    if (pick.source === "library") {
      try {
        const res = await binderSetSlot(token, page, toApiSlot(toSlot), pick.cardId);
        setBinder(res);
        setMsg("");
        setPick(null);
      } catch (err) {
        setMsg(err instanceof Error ? err.message : String(err));
      }
      return;
    }
    if (pick.source !== "slot") return;
    if (pick.slot === toSlot) {
      setPick(null);
      return;
    }
    try {
      const res = await binderSwap(token, page, toApiSlot(pick.slot), toApiSlot(toSlot));
      setBinder(res);
      setMsg("");
      setPick(null);
    } catch (err) {
      setMsg(err instanceof Error ? err.message : String(err));
    }
  }

  function onTapLibraryCard(cardId: string) {
    setPick((prev) =>
      prev?.source === "library" && prev.cardId === cardId ? null : { source: "library", cardId },
    );
  }

  function onTapSlot(idx: number, cid: string | null) {
    if (pick) {
      void applyPickToSlot(idx);
      return;
    }
    if (!cid) return;
    setPick({ source: "slot", slot: idx, cardId: cid });
  }

  async function addToFirstEmpty(cardId: string) {
    if (!token) return;
    const empty = slots.findIndex((x) => !x);
    if (empty < 0) {
      setMsg(t("binder.wall_full"));
      return;
    }
    try {
      const res = await binderSetSlot(token, page, toApiSlot(empty), cardId);
      setBinder(res);
      setMsg("");
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  }

  async function onDropSlot(toSlot: number, e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (!token) {
      clearDrag();
      return;
    }

    const payload = readDrag(e);
    clearDrag();
    if (!payload?.cardId) return;

    // From collection: keep collection card; empty slot → place; occupied → replace.
    if (payload.source === "library") {
      try {
        const res = await binderSetSlot(token, page, toApiSlot(toSlot), payload.cardId);
        setBinder(res);
        setMsg("");
      } catch (err) {
        setMsg(err instanceof Error ? err.message : String(err));
      }
      return;
    }

    // From binder slot.
    if (payload.source !== "slot") return;
    if (payload.slot === toSlot) return;

    const targetCard = slots[toSlot] || null;

    try {
      if (!targetCard) {
        // Empty target: move card there, clear original slot.
        const res = await binderSwap(token, page, toApiSlot(payload.slot), toApiSlot(toSlot));
        setBinder(res);
      } else {
        // Occupied: swap card IDs between the two slots.
        const res = await binderSwap(token, page, toApiSlot(payload.slot), toApiSlot(toSlot));
        setBinder(res);
      }
      setMsg("");
    } catch (err) {
      setMsg(err instanceof Error ? err.message : String(err));
    }
  }

  async function removeSlot(slot: number) {
    if (!token) return;
    try {
      const res = await binderSetSlot(token, page, toApiSlot(slot), null);
      setBinder(res);
      setMsg("");
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  }

  async function onDropTrash(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    const payload = readDrag(e);
    clearDrag();
    if (!payload || payload.source !== "slot") return;
    await removeSlot(payload.slot);
  }

  function renderSheet(start: number) {
    return (
      <div className="binder-sheet">
        <div className="binder-sheet-grid">
          {Array.from({ length: 9 }, (_, i) => {
            const idx = start + i;
            const cid = slots[idx] || null;
            const isDragging =
              dragPayload?.source === "slot" && dragPayload.slot === idx;
            const isPicked =
              (pick?.source === "slot" && pick.slot === idx) ||
              (pick?.source === "library" && !!pick.cardId && pick.cardId === cid);
            return (
              <div
                key={idx}
                className={`binder-pocket ${isDragging ? "dragging" : ""} ${isPicked ? "pick-selected" : ""} ${cid ? "filled" : "empty-slot"}`}
                onDragOver={(e) => {
                  e.preventDefault();
                  e.dataTransfer.dropEffect = "move";
                }}
                onDrop={(e) => onDropSlot(idx, e)}
                onClick={() => onTapSlot(idx, cid)}
                onDoubleClick={() => cid && removeSlot(idx)}
                title={
                  cid
                    ? `${displayCardId(cid)} · ${t("binder.slot_title_filled")}`
                    : t("binder.slot_title_empty", { n: idx + 1 })
                }
              >
                {cid ? (
                  <div
                    className="binder-pocket-card"
                    draggable
                    onDragStart={(e) => {
                      e.stopPropagation();
                      beginDrag({ source: "slot", slot: idx, cardId: cid }, e);
                    }}
                    onDragEnd={clearDrag}
                  >
                    <CardImg cardId={cid} alt="" className="binder-pocket-img" loading="lazy" />
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  if (!ready) {
    return (
      <div className="stack">
        <h1 className="page-title">{t("page.binder")}</h1>
        <p className="muted">…</p>
      </div>
    );
  }
  if (!isLoggedIn) {
    return (
      <div className="stack">
        <h1 className="page-title">{t("page.binder")}</h1>
        <LoginGate title={t("binder.login_title")} body={t("binder.login_body")} />
      </div>
    );
  }

  return (
    <div className="stack">
      <h1 className="page-title">{t("page.binder")}</h1>
      <div className="binder-workspace">
        <section className="deck-panel binder-panel binder-main">
          <div className="collector-stats-grid binder-stats">
            <div className="collector-stat-card">
              <span className="muted">{t("binder.page_label")}</span>
              <strong>
                {page} / 10
              </strong>
            </div>
            <div className="collector-stat-card">
              <span className="muted">{t("binder.filled_slots")}</span>
              <strong>
                {filledSlots} / 18
              </strong>
            </div>
            <div className="collector-stat-card full">
              <span className="muted">
                {t("binder.stats", {
                  unique: collection?.total_unique || 0,
                  copies: collection?.total_copies || 0,
                })}
              </span>
            </div>
          </div>

          <div className="binder-controls">
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={t("binder.page_title")}
            />
            <button
              type="button"
              onClick={async () => {
                if (!token) return;
                try {
                  const res = await binderSetPageTitle(token, page, title);
                  setBinder(res);
                  setMsg("");
                } catch (e) {
                  setMsg(e instanceof Error ? e.message : String(e));
                }
              }}
            >
              {t("binder.save_title")}
            </button>
            <button
              type="button"
              className="btn-add"
              onClick={async () => {
                if (!token) return;
                if (!window.confirm(t("binder.autofill_confirm"))) return;
                try {
                  const res = await binderAutofillPage(token, page);
                  setBinder(res);
                  setMsg("");
                } catch (e) {
                  setMsg(e instanceof Error ? e.message : String(e));
                }
              }}
            >
              {t("binder.autofill")}
            </button>
            <button
              type="button"
              className="btn-danger"
              onClick={async () => {
                if (!token) return;
                try {
                  const res = await binderClearPage(token, page);
                  setBinder(res);
                  setMsg("");
                } catch (e) {
                  setMsg(e instanceof Error ? e.message : String(e));
                }
              }}
            >
              {t("binder.clear_wall")}
            </button>
          </div>

          <h2 className="deck-section-title">{t("binder.wall_heading", { page })}</h2>
          <p className="muted binder-hint">{t("binder.drag_hint")}</p>
          {msg ? <p style={{ color: "#fca5a5", marginBottom: "0.45rem" }}>{msg}</p> : null}
          <div className="binder-spread">
            {renderSheet(0)}
            {renderSheet(9)}
          </div>
          <div className="binder-pagination">
            <div
              className={`binder-trash-zone ${trashHot ? "hot" : ""} ${
                dragPayload?.source === "slot" ? "ready" : ""
              }`}
              title={t("binder.trash_hint")}
              onDragOver={(e) => {
                const payload = dragRef.current;
                if (!payload || payload.source !== "slot") return;
                e.preventDefault();
                e.dataTransfer.dropEffect = "move";
                if (!trashHot) setTrashHot(true);
              }}
              onDragLeave={(e) => {
                if (!e.currentTarget.contains(e.relatedTarget as Node)) {
                  setTrashHot(false);
                }
              }}
              onDrop={onDropTrash}
              aria-label={t("binder.trash_hint")}
            >
              <div className="binder-trash">
                <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
                  <path
                    fill="currentColor"
                    d="M9 3h6l1 2h4v2H4V5h4l1-2zm1 6h2v9h-2V9zm4 0h2v9h-2V9zM7 9h2v9H7V9zm-1 12h12a1 1 0 0 0 1-1V8H5v12a1 1 0 0 0 1 1z"
                  />
                </svg>
              </div>
              <span className="binder-trash-label">{t("binder.trash_label")}</span>
            </div>
            <div className="binder-pagination-nav">
              <button type="button" className="secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                ‹
              </button>
              <select value={page} onChange={(e) => setPage(Number(e.target.value))}>
                {Array.from({ length: 10 }, (_, i) => i + 1).map((p) => (
                  <option key={p} value={p}>
                    {p} / 10
                  </option>
                ))}
              </select>
              <button type="button" className="secondary" disabled={page >= 10} onClick={() => setPage((p) => p + 1)}>
                ›
              </button>
            </div>
            <button
              type="button"
              className={`binder-share-zone${shareBusy ? " is-busy" : ""}`}
              disabled={shareBusy}
              onClick={() => void openShare()}
              title={t("binder.share")}
              aria-label={t("binder.share")}
              aria-busy={shareBusy}
            >
              <div className="binder-share-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" width="18" height="18">
                  <path
                    fill="currentColor"
                    d="M18 16.08c-.76 0-1.44.3-1.96.77L8.91 12.7c.05-.23.09-.46.09-.7s-.04-.47-.09-.7l7.05-4.11A2.99 2.99 0 0 0 18 7.91c1.66 0 3-1.34 3-3s-1.34-3-3-3-3 1.34-3 3c0 .24.04.47.09.7L8.04 9.81A2.99 2.99 0 0 0 6 9c-1.66 0-3 1.34-3 3s1.34 3 3 3c.79 0 1.5-.31 2.04-.81l7.12 4.15c-.05.21-.08.43-.08.66 0 1.61 1.31 2.92 2.92 2.92s2.92-1.31 2.92-2.92-1.31-2.92-2.92-2.92z"
                  />
                </svg>
              </div>
              <span className="binder-share-label">{t("binder.share")}</span>
            </button>
          </div>
        </section>

        <section className="deck-panel binder-library">
          <h2 className="deck-section-title">{t("page.collector")}</h2>
          <p className="muted binder-hint">{t("binder.add_hint")}</p>
          {pick ? (
            <div className="deck-login-hint">
              <p className="muted">{t("binder.tap_hint")}</p>
              <button type="button" className="secondary" onClick={() => setPick(null)}>
                {t("binder.clear_pick")}
              </button>
            </div>
          ) : null}
          <div className="collector-tools">
            <input
              type="search"
              enterKeyHint="search"
              value={collQuery}
              onChange={(e) => setCollQuery(e.target.value)}
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
              placeholder={t("binder.search_ph")}
              className="collector-search"
              aria-label={t("binder.search_ph")}
            />
            <select
              className="collector-sort"
              value={collSort}
              onChange={(e) => setCollSort(e.target.value as CollSort)}
            >
              <option value="id_asc">{t("collector.sort_id_asc")}</option>
              <option value="id_desc">{t("collector.sort_id_desc")}</option>
              <option value="qty_desc">{t("collector.sort_qty_desc")}</option>
              <option value="qty_asc">{t("collector.sort_qty_asc")}</option>
              <option value="rarity_desc">{t("collector.sort_rarity_desc")}</option>
              <option value="rarity_asc">{t("collector.sort_rarity_asc")}</option>
            </select>
          </div>
          <p className="muted binder-hint">
            {t("binder.showing", { shown: shownCollEntries.length, total: filteredCollEntries.length })}
          </p>
          {!shownCollEntries.length ? (
            <p className="muted">{t("binder.no_cards")}</p>
          ) : (
            <div className="collector-grid">
              {shownCollEntries.map(([id]) => (
                <article
                  key={id}
                  className={`collector-card binder-library-card ${
                    dragPayload?.source === "library" && dragPayload.cardId === id ? "dragging" : ""
                  } ${pick?.source === "library" && pick.cardId === id ? "pick-selected" : ""}`}
                  draggable
                  onDragStart={(e) => beginDrag({ source: "library", cardId: id }, e)}
                  onDragEnd={clearDrag}
                  onClick={() => onTapLibraryCard(id)}
                >
                  <div className="collector-art">
                    <CardImg cardId={id} alt="" loading="lazy" />
                  </div>
                  <div className="collector-meta">
                    <strong>{displayCardId(id)}</strong>
                    {metaById[id]?.rarity ? <span className="count">{metaById[id].rarity}</span> : null}
                  </div>
                  <div className="collector-actions" style={{ gridTemplateColumns: "1fr" }}>
                    <button
                      type="button"
                      className="btn-add"
                      onClick={(e) => {
                        e.stopPropagation();
                        addToFirstEmpty(id);
                      }}
                    >
                      {t("binder.add")}
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
          {hasMoreColl ? (
            <div className="collector-more-wrap">
              <button type="button" className="secondary" onClick={() => setCollVisible((v) => v + 120)}>
                {t("collector.show_more")}
              </button>
            </div>
          ) : null}
        </section>
      </div>

      {shareOpen ? (
        <div
          className="deck-details-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setShareOpen(false);
          }}
        >
          <section className="deck-import-modal" role="dialog" aria-modal="true" aria-labelledby="binder-share-title">
            <div className="deck-details-head">
              <h2 id="binder-share-title">{t("binder.share")}</h2>
              <button type="button" className="ghost" onClick={() => setShareOpen(false)} aria-label="×">
                ×
              </button>
            </div>
            <p className="muted deck-import-hint">{t("binder.share_hint")}</p>
            {sharePhoto ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img className="binder-share-photo" src={sharePhoto} alt={t("binder.share_photo")} />
            ) : null}
            <input className="deck-share-url" readOnly value={shareUrl} onFocus={(e) => e.currentTarget.select()} />
            <div className="deck-details-actions">
              <button type="button" onClick={downloadSharePhoto} disabled={!sharePhoto}>
                {t("binder.share_save_photo")}
              </button>
              <button type="button" className="secondary" onClick={() => void copyShareLink()}>
                {t("binder.share_copy")}
              </button>
              <button type="button" className="secondary" onClick={() => setShareOpen(false)}>
                {t("deck.save_cancel")}
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
