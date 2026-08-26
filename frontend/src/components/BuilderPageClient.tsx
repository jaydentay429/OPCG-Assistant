"use client";

import Link from "next/link";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  cardImageUrl,
  createDeck,
  deleteDeck,
  fetchDeckStatsBatch,
  fetchDecks,
  updateDeck,
  type BatchPriceFields,
  type DeckStatFields,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cardIdSortKey, displayCardId } from "@/lib/cardId";
import { copyTextToClipboard } from "@/lib/clipboard";
import { isLeaderType, useDeck } from "@/lib/deck";
import { buildDeckImage, downloadDeckImage } from "@/lib/deckExport";
import { buildDeckShareUrl, buildDeckShareUrlCompact, parseDeckListText, parseDeckShareFromSearch } from "@/lib/deckShare";
import { summarizeDeckStructure } from "@/lib/deckStructure";
import { localizeFilterToken } from "@/lib/filterLabels";
import { useI18n } from "@/lib/i18n";
import { formatYen, loadUnitPrices, sumPricedCopies, unitPriceOf } from "@/lib/priceCalc";
import { consumeSkipScrollRestore, flushCurrentScroll, readPathScrollTarget, requestScrollRestore, scrollYForPersist } from "@/lib/scrollRestore";
import type { Deck } from "@/lib/types";
import QRCode from "qrcode";
import { SearchPageClient } from "./SearchPageClient";

const BUILDER_SECTIONS_KEY = "opcg_builder_sections_v1";
const BUILDER_SCROLL_KEY = "opcg_builder_scroll_v1";

function formatUpdatedAt(raw: string, lang: string): string {
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return "";
  try {
    return new Intl.DateTimeFormat(lang === "en" ? "en" : lang === "zh-Hans" ? "zh-CN" : "zh-TW", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(d);
  } catch {
    return d.toLocaleString();
  }
}

export function BuilderPageClient() {
  const { t, lang } = useI18n();
  const { token, isLoggedIn, ready, requestLogin } = useAuth();
  const draft = useDeck();
  const searchParams = useSearchParams();
  const [decks, setDecks] = useState<Deck[]>([]);
  const [saveChoice, setSaveChoice] = useState(false);
  const [saveOverwritePick, setSaveOverwritePick] = useState(false);
  const [msg, setMsg] = useState("");
  const [exporting, setExporting] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [importText, setImportText] = useState("");
  const [importing, setImporting] = useState(false);
  const [copyText, setCopyText] = useState("");
  const [showPrices, setShowPrices] = useState(false);
  const [priceMap, setPriceMap] = useState<Record<string, BatchPriceFields>>({});
  const [pricesLoading, setPricesLoading] = useState(false);
  const [previewUrl, setPreviewUrl] = useState("");
  const [previewBlob, setPreviewBlob] = useState<Blob | null>(null);
  const [previewTitle, setPreviewTitle] = useState("");
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [shareOpen, setShareOpen] = useState(false);
  const [shareUrl, setShareUrl] = useState("");
  const [shareQr, setShareQr] = useState("");
  const [statsMap, setStatsMap] = useState<Record<string, DeckStatFields>>({});
  const [sectionLibOpen, setSectionLibOpen] = useState(true);
  const [sectionAddOpen, setSectionAddOpen] = useState(true);
  const saveMenuRef = useRef<HTMLDivElement | null>(null);
  const lastImportedShare = useRef<string>("");
  const previewUrlRef = useRef("");
  const previewRunRef = useRef(0);
  const pendingRestoreYRef = useRef(0);
  const pendingAnchorRef = useRef("");
  const restoreOnceRef = useRef(false);

  const reload = useCallback(async () => {
    if (!token) {
      setDecks([]);
      return;
    }
    const res = await fetchDecks(token);
    setDecks(res.decks || []);
  }, [token]);

  useLayoutEffect(() => {
    try {
      const raw = window.localStorage.getItem(BUILDER_SECTIONS_KEY);
      if (raw) {
        const saved = JSON.parse(raw) as { lib?: unknown; add?: unknown };
        if (typeof saved.lib === "boolean") setSectionLibOpen(saved.lib);
        if (typeof saved.add === "boolean") setSectionAddOpen(saved.add);
      }
    } catch {
      /* ignore */
    }
    try {
      if (!consumeSkipScrollRestore()) {
        const target = readPathScrollTarget("/builder");
        pendingRestoreYRef.current = target.y;
        pendingAnchorRef.current = target.anchor || "";
      } else {
        pendingRestoreYRef.current = 0;
        pendingAnchorRef.current = "";
        restoreOnceRef.current = true;
      }
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem(
        BUILDER_SECTIONS_KEY,
        JSON.stringify({ lib: sectionLibOpen, add: sectionAddOpen }),
      );
    } catch {
      /* ignore */
    }
  }, [sectionLibOpen, sectionAddOpen]);

  useEffect(() => {
    const saveY = (e?: Event) => {
      try {
        const detail = (e as CustomEvent<{ y?: number; anchor?: string }> | undefined)?.detail;
        const current = typeof detail?.y === "number" ? detail.y : window.scrollY || 0;
        const y = scrollYForPersist(pendingRestoreYRef.current, current);
        const anchor =
          (typeof detail?.anchor === "string" && detail.anchor) ||
          pendingAnchorRef.current ||
          "";
        if (typeof detail?.anchor === "string" && detail.anchor) {
          pendingAnchorRef.current = detail.anchor;
        }
        window.sessionStorage.setItem(
          BUILDER_SCROLL_KEY,
          JSON.stringify({ y, anchor }),
        );
      } catch {
        /* ignore */
      }
    };
    saveY();
    window.addEventListener("scroll", saveY, { passive: true });
    window.addEventListener("pagehide", saveY);
    window.addEventListener("opcg:flush-scroll", saveY as EventListener);
    document.addEventListener("visibilitychange", saveY);
    return () => {
      window.removeEventListener("scroll", saveY);
      window.removeEventListener("pagehide", saveY);
      window.removeEventListener("opcg:flush-scroll", saveY as EventListener);
      document.removeEventListener("visibilitychange", saveY);
    };
  }, []);

  useLayoutEffect(() => {
    if (!ready || restoreOnceRef.current) return;
    if (!pendingRestoreYRef.current && !pendingAnchorRef.current) return;
    restoreOnceRef.current = true;
    const y = pendingRestoreYRef.current;
    const anchor = pendingAnchorRef.current;
    requestScrollRestore({ y, anchor }, () => {
      pendingRestoreYRef.current = 0;
      pendingAnchorRef.current = "";
    });
  }, [ready, sectionAddOpen, sectionLibOpen]);

  const structureIdsKey = useMemo(() => {
    const ids = Object.keys(draft.cards).filter((id) => Number(draft.cards[id]) > 0);
    if (draft.leader) ids.unshift(draft.leader);
    return [...new Set(ids)].sort().join("|");
  }, [draft.leader, draft.cards]);

  useEffect(() => {
    const ids = structureIdsKey ? structureIdsKey.split("|").filter(Boolean) : [];
    if (!ids.length) {
      setStatsMap({});
      return;
    }
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const load = (attempt: number) => {
      fetchDeckStatsBatch(ids)
        .then((map) => {
          if (!cancelled) setStatsMap(map || {});
        })
        .catch(() => {
          if (cancelled) return;
          setStatsMap({});
          if (attempt < 6) timer = setTimeout(() => load(attempt + 1), 1500);
        });
    };
    load(0);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [structureIdsKey]);

  useEffect(() => {
    if (!ready) return;
    reload().catch(() => setDecks([]));
  }, [ready, reload]);

  // QR always contains the full ?d=... link. Each scan opens it again and reloads the deck.
  useEffect(() => {
    if (!draft.ready) return;
    const shareKey =
      searchParams.get("d") ||
      searchParams.get("deck") ||
      [searchParams.get("n"), searchParams.get("l"), searchParams.get("c")].filter(Boolean).join("|");
    if (!shareKey) return;
    if (shareKey === lastImportedShare.current) return;

    const shared = parseDeckShareFromSearch(searchParams.toString());
    if (!shared) return;

    lastImportedShare.current = shareKey;
    draft.importDeck(shared);
    setMsg(t("deck.import_ok"));
  }, [draft.ready, draft.importDeck, searchParams, t]);

  useEffect(() => {
    if (!saveChoice) {
      setSaveOverwritePick(false);
      return;
    }
    const onPointerDown = (e: PointerEvent) => {
      const root = saveMenuRef.current;
      if (!root) return;
      if (e.target instanceof Node && root.contains(e.target)) return;
      setSaveChoice(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [saveChoice]);

  useEffect(() => {
    return () => {
      if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    };
  }, []);

  const sortedDecks = useMemo(() => {
    return [...decks].sort((a, b) => {
      const ta = Date.parse(a.updated_at || a.created_at || "") || 0;
      const tb = Date.parse(b.updated_at || b.created_at || "") || 0;
      return tb - ta;
    });
  }, [decks]);

  async function doSave(mode: "auto" | "new" | "update", targetDeckId?: string) {
    if (!token) {
      setMsg(t("deck.save_login_draft"));
      requestLogin();
      return;
    }
    const name = draft.name.trim() || (mode === "auto" && !draft.editingId ? t("deck.new_deck_default") : "");
    if (!name) {
      setMsg(t("deck.save_name_required"));
      return;
    }
    try {
      const updateId =
        mode === "update"
          ? targetDeckId || draft.editingId
          : mode === "auto"
            ? draft.editingId
            : null;
      if (updateId) {
        const updated = await updateDeck(token, updateId, {
          name,
          leader_card_id: draft.leader,
          cards: draft.cards,
        });
        draft.loadDeck(updated);
        setMsg(t("deck.save_updated"));
      } else if (mode === "update") {
        setSaveOverwritePick(true);
        return;
      } else {
        const created = await createDeck(token, {
          name,
          leader_card_id: draft.leader,
          cards: draft.cards,
        });
        draft.loadDeck(created);
        setMsg(t("deck.save_created"));
      }
      setSaveChoice(false);
      setSaveOverwritePick(false);
      await reload();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  }

  async function onNewDraft() {
    setSaveChoice(false);
    setSaveOverwritePick(false);
    setMsg("");
    if (!token) {
      draft.clearDraft();
      setMsg(t("deck.save_login_draft"));
      return;
    }
    try {
      const created = await createDeck(token, {
        name: t("deck.new_deck_default"),
        leader_card_id: null,
        cards: {},
      });
      draft.loadDeck(created);
      await reload();
      setMsg(t("deck.new_draft_created"));
    } catch (e) {
      draft.clearDraft();
      setMsg(e instanceof Error ? e.message : String(e));
    }
  }

  async function onDeleteDeck(deckId: string) {
    if (!token || !deckId) return;
    try {
      await deleteDeck(token, deckId);
      if (draft.editingId === deckId) draft.clearDraft();
      setConfirmDeleteId(null);
      setMsg(t("deck.deleted"));
      await reload();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  }

  function exportLabels() {
    return {
      title: t("deck.unnamed"),
      leader: t("deck.leader_short"),
      noLeader: t("deck.no_leader"),
      cardsN: t("deck.export_cards_n", { count: draft.nonLeaderTotal }),
      uniqueN: t("deck.export_kinds_n", {
        count: Object.keys(draft.cards).length + (draft.leader ? 1 : 0),
      }),
      costCurve: t("deck.export_cost"),
      powerCurve: t("deck.export_power"),
      counterCurve: t("deck.curve_counter"),
      createdBy: t("deck.export_created"),
      qty: "×",
    };
  }

  function exportInput() {
    return {
      name: draft.name.trim() || t("deck.unnamed"),
      leader: draft.leader,
      cards: draft.cards,
      lang,
      labels: exportLabels(),
    };
  }

  function clearPreview() {
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    previewUrlRef.current = "";
    setPreviewUrl("");
    setPreviewBlob(null);
    setPreviewTitle("");
  }

  function closeDeckDetails() {
    previewRunRef.current += 1;
    setDetailsOpen(false);
    setExporting(false);
    clearPreview();
  }

  async function onOpenDeckDetails() {
    if (!draft.leader && !Object.keys(draft.cards).length) {
      setMsg(t("deck.export_empty"));
      return;
    }
    const runId = previewRunRef.current + 1;
    previewRunRef.current = runId;
    clearPreview();
    setDetailsOpen(true);
    setExporting(true);
    setMsg(t("deck.exporting"));
    try {
      const result = await buildDeckImage(exportInput());
      if (previewRunRef.current !== runId) return;
      const url = URL.createObjectURL(result.blob);
      previewUrlRef.current = url;
      setPreviewUrl(url);
      setPreviewBlob(result.blob);
      setPreviewTitle(result.title);
      setMsg("");
    } catch (e) {
      if (previewRunRef.current !== runId) return;
      setMsg(e instanceof Error ? e.message : t("deck.export_fail"));
    } finally {
      if (previewRunRef.current === runId) setExporting(false);
    }
  }

  async function onDownloadDeck() {
    if (!previewBlob || !previewTitle) return;
    setExporting(true);
    try {
      await downloadDeckImage(exportInput(), previewBlob, previewTitle);
      setMsg(t("deck.export_ok"));
    } catch (e) {
      setMsg(e instanceof Error ? e.message : t("deck.export_fail"));
    } finally {
      setExporting(false);
    }
  }

  function deckListText() {
    const lines: string[] = [];
    if (draft.leader) lines.push(`Leader: ${displayCardId(draft.leader)}`);
    for (const [id, n] of Object.entries(draft.cards).sort((a, b) =>
      cardIdSortKey(a[0]).localeCompare(cardIdSortKey(b[0])),
    )) {
      lines.push(`${displayCardId(id)} x${n}`);
    }
    return lines.join("\n");
  }

  async function copyList() {
    const text = deckListText();
    if (!text) {
      setMsg(t("deck.export_empty"));
      return;
    }
    if (await copyTextToClipboard(text)) {
      setMsg(t("deck.copy_ok"));
      return;
    }
    // Browsers block clipboard writes over plain http — show the text instead.
    setCopyText(text);
    setMsg(t("deck.copy_manual"));
  }

  /**
   * Pasted lists often omit a `Leader:` marker, so look the ids up and move a
   * leader-typed card out of the main deck before merging.
   */
  async function resolveLeader(parsed: {
    name: string;
    leader: string | null;
    cards: Record<string, number>;
  }) {
    if (parsed.leader) return parsed;
    const ids = Object.keys(parsed.cards);
    if (!ids.length) return parsed;
    let stats: Record<string, { card_type?: string | null }> = {};
    try {
      stats = await fetchDeckStatsBatch(ids);
    } catch {
      return parsed;
    }
    const leaderId = ids.find((id) => isLeaderType(stats[id]?.card_type));
    if (!leaderId) return parsed;
    const cards = { ...parsed.cards };
    delete cards[leaderId];
    return { ...parsed, leader: leaderId, cards };
  }

  async function onApplyImport() {
    const initial = parseDeckListText(importText);
    if (!initial) {
      setMsg(t("deck.import_fail"));
      return;
    }
    setImporting(true);
    try {
      const parsed = await resolveLeader(initial);
      const leaderApplied = Boolean(parsed.leader && !draft.leader);
      const { added, skipped } = draft.mergeIntoDeck(parsed);
      if (added <= 0 && !leaderApplied) {
        setMsg(skipped > 0 ? t("deck.import_skipped") : t("deck.import_fail"));
        return;
      }
      setImportOpen(false);
      setImportText("");
      if (skipped > 0) {
        setMsg(t("deck.import_partial", { added: String(added), skipped: String(skipped) }));
      } else {
        const count = added + (leaderApplied ? 1 : 0);
        setMsg(t("deck.import_paste_ok", { count: String(count) }));
      }
    } finally {
      setImporting(false);
    }
  }

  const entries = Object.entries(draft.cards)
    .filter(([, n]) => Number(n) > 0)
    .sort((a, b) => cardIdSortKey(a[0]).localeCompare(cardIdSortKey(b[0])));

  const priceIdsKey = useMemo(() => {
    const ids = Object.keys(draft.cards).filter((id) => Number(draft.cards[id]) > 0);
    if (draft.leader) ids.unshift(draft.leader);
    return [...new Set(ids)].sort().join("|");
  }, [draft.leader, draft.cards]);

  useEffect(() => {
    if (!showPrices) return;
    const ids = priceIdsKey ? priceIdsKey.split("|").filter(Boolean) : [];
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
  }, [showPrices, priceIdsKey]);

  const deckPriceSummary = useMemo(() => {
    if (!showPrices) return null;
    const cards: Record<string, number> = { ...draft.cards };
    if (draft.leader) cards[draft.leader] = (cards[draft.leader] || 0) + 1;
    return sumPricedCopies(cards, priceMap);
  }, [showPrices, draft.cards, draft.leader, priceMap]);

  const structure = useMemo(
    () => summarizeDeckStructure(draft.leader, draft.cards, statsMap, lang),
    [draft.leader, draft.cards, statsMap, lang],
  );

  async function openShare() {
    if (!draft.leader && !Object.keys(draft.cards).length) {
      setMsg(t("deck.export_empty"));
      return;
    }
    const payload = {
      name: draft.name.trim(),
      leader: draft.leader,
      cards: draft.cards,
    };
    const url = buildDeckShareUrl(payload);
    const compact = buildDeckShareUrlCompact(payload);
    setShareUrl(url);
    try {
      const dataUrl = await QRCode.toDataURL(compact, {
        margin: 1,
        width: 220,
        color: { dark: "#0f172a", light: "#ffffff" },
      });
      setShareQr(dataUrl);
    } catch {
      setShareQr("");
    }
    setShareOpen(true);
  }

  async function copyShareLink() {
    if (!shareUrl) return;
    if (await copyTextToClipboard(shareUrl)) {
      setMsg(t("deck.share_copied"));
      return;
    }
    setCopyText(shareUrl);
    setMsg(t("deck.copy_manual"));
  }

  const progressPct = Math.min(100, Math.round((draft.nonLeaderTotal / 50) * 100));
  const editingName = draft.name.trim() || (draft.editingId ? t("deck.unnamed") : t("deck.target_new"));

  return (
    <div className="stack">
      <h1 className="page-title">{t("page.builder")}</h1>

      <section className="deck-panel deck-library">
        <div className="deck-section-head">
          <div>
            <h2 className="deck-section-title">{t("deck.pick_label")}</h2>
            <p className="muted deck-section-sub">{t("deck.pick_sub")}</p>
          </div>
          <div className="deck-section-head-actions">
            <button type="button" className="secondary" onClick={() => setSectionLibOpen((v) => !v)}>
              {sectionLibOpen ? t("deck.section_collapse") : t("deck.section_expand")}
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => void onNewDraft()}
            >
              {t("deck.new_draft")}
            </button>
          </div>
        </div>

        {sectionLibOpen ? (
          <>
        {!isLoggedIn ? (
          <div className="deck-login-hint">
            <p className="muted">{t("deck.view_login_draft")}</p>
            <button type="button" className="secondary" onClick={() => requestLogin()}>
              {t("auth.login")}
            </button>
          </div>
        ) : !sortedDecks.length ? (
          <div className="deck-empty">
            <p className="muted">{t("deck.pick_empty")}</p>
            <p className="muted">{t("deck.pick_empty_hint")}</p>
          </div>
        ) : (
          <div className="deck-card-grid">
            {sortedDecks.map((d) => {
              const active = draft.editingId === d.id;
              const count = Number(d.non_leader_count) || 0;
              const pct = Math.min(100, Math.round((count / 50) * 100));
              const updated = formatUpdatedAt(d.updated_at || d.created_at || "", lang);
              return (
                <article key={d.id} className={`deck-card${active ? " active" : ""}`}>
                  <button
                    type="button"
                    className="deck-card-main"
                    onClick={() => {
                      draft.loadDeck(d);
                      setConfirmDeleteId(null);
                      setMsg("");
                    }}
                  >
                    <div className="deck-card-art">
                      {d.leader_card_id ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={cardImageUrl(d.leader_card_id)} alt={d.leader_card_id} />
                      ) : (
                        <div className="deck-card-art-empty">{t("deck.no_leader")}</div>
                      )}
                    </div>
                    <div className="deck-card-body">
                      <div className="deck-card-title-row">
                        <h3 className="deck-card-title">{d.name || t("deck.unnamed")}</h3>
                        {active ? <span className="deck-badge editing">{t("deck.badge_editing")}</span> : null}
                        {d.is_valid_ready ? (
                          <span className="deck-badge ready">{t("deck.badge_ready")}</span>
                        ) : (
                          <span className="deck-badge draft">{t("deck.badge_incomplete")}</span>
                        )}
                      </div>
                      <div className="deck-card-meta muted">
                        <span>
                          {t("deck.leader_short")}:{" "}
                          {d.leader_card_id ? displayCardId(d.leader_card_id) : "—"}
                        </span>
                        {updated ? <span>{t("deck.updated", { time: updated })}</span> : null}
                      </div>
                      <div className="deck-progress">
                        <div className="deck-progress-track">
                          <div className="deck-progress-fill" style={{ width: `${pct}%` }} />
                        </div>
                        <span className="deck-progress-label">{count}/50</span>
                      </div>
                    </div>
                  </button>
                  <div className="deck-card-actions">
                    <button
                      type="button"
                      onClick={() => {
                        draft.loadDeck(d);
                        setConfirmDeleteId(null);
                      }}
                    >
                      {active ? t("deck.editing_now") : t("deck.open_edit")}
                    </button>
                    {confirmDeleteId === d.id ? (
                      <>
                        <button type="button" className="danger" onClick={() => onDeleteDeck(d.id)}>
                          {t("deck.delete_confirm")}
                        </button>
                        <button type="button" className="ghost" onClick={() => setConfirmDeleteId(null)}>
                          {t("deck.save_cancel")}
                        </button>
                      </>
                    ) : (
                      <button type="button" className="btn-danger" onClick={() => setConfirmDeleteId(d.id)}>
                        {t("deck.delete")}
                      </button>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        )}
          </>
        ) : null}
      </section>

      <section className="deck-panel deck-editor">
        <div className="deck-section-head">
          <div>
            <h2 className="deck-section-title">{t("deck.editor_title")}</h2>
            <p className="muted deck-section-sub">
              {t("deck.editor_sub", { name: editingName })}
            </p>
          </div>
        </div>

        <div className="deck-editor-top">
          {draft.leader ? (
            <div className="deck-editor-leader">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={cardImageUrl(draft.leader)} alt={draft.leader} />
              <div>
                <div className="muted">{t("deck.leader_short")}</div>
                <strong>{displayCardId(draft.leader)}</strong>
              </div>
            </div>
          ) : (
            <div className="deck-editor-leader empty">
              <div className="deck-card-art-empty sm">{t("deck.no_leader")}</div>
              <span className="muted">{t("deck.pick_leader_hint")}</span>
            </div>
          )}

          <div className="deck-editor-fields">
            <label className="deck-field-label" htmlFor="deck-name-input">
              {t("deck.name_label")}
            </label>
            <div className="deck-save-row">
              <input
                id="deck-name-input"
                value={draft.name}
                onChange={(e) => draft.setName(e.target.value)}
                placeholder={t("deck.name_ph")}
              />
              <div className="deck-save-menu" ref={saveMenuRef}>
                <button
                  type="button"
                  aria-expanded={saveChoice}
                  aria-haspopup="menu"
                  onClick={() => setSaveChoice((v) => !v)}
                >
                  {t("deck.save")}
                </button>
                {saveChoice ? (
                  <div className="deck-save-menu-panel" role="menu">
                    {!isLoggedIn ? (
                      <p className="muted deck-save-menu-hint">{t("deck.save_login")}</p>
                    ) : null}
                    {isLoggedIn && draft.editingId ? (
                      <button type="button" role="menuitem" onClick={() => void doSave("auto")}>
                        {t("deck.save_update")}
                      </button>
                    ) : null}
                    {isLoggedIn && sortedDecks.length ? (
                      <button
                        type="button"
                        role="menuitem"
                        className="secondary"
                        onClick={() => setSaveOverwritePick((v) => !v)}
                      >
                        {t("deck.save_overwrite")}
                      </button>
                    ) : null}
                    {saveOverwritePick && isLoggedIn ? (
                      <div className="deck-save-overwrite-list">
                        <p className="muted deck-save-menu-hint">{t("deck.save_overwrite_hint")}</p>
                        {sortedDecks.map((d) => (
                          <button
                            key={d.id}
                            type="button"
                            role="menuitem"
                            className={d.id === draft.editingId ? "active" : undefined}
                            onClick={() => void doSave("update", d.id)}
                          >
                            {(d.name || t("deck.unnamed")) +
                              (d.leader_card_id ? ` · ${displayCardId(d.leader_card_id)}` : "")}
                          </button>
                        ))}
                      </div>
                    ) : null}
                    <button type="button" role="menuitem" onClick={() => void doSave("new")}>
                      {t("deck.save_new")}
                    </button>
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => setSaveChoice(false)}
                    >
                      {t("deck.save_cancel")}
                    </button>
                  </div>
                ) : null}
              </div>
            </div>
            <div className="deck-progress editor">
              <div className="deck-progress-track">
                <div className="deck-progress-fill" style={{ width: `${progressPct}%` }} />
              </div>
              <span className="deck-progress-label">
                {t("deck.target_stats", { count: draft.nonLeaderTotal })}
              </span>
            </div>
          </div>
        </div>

        <div className="deck-toolbar">
          <div className="deck-toolbar-group">
            <button type="button" className="deck-tool-neutral" onClick={() => setImportOpen(true)}>
              {t("deck.import")}
            </button>
            <button type="button" className="deck-tool-neutral" onClick={copyList}>
              {t("deck.copy_list")}
            </button>
            <button
              type="button"
              className="deck-tool-neutral"
              onClick={() => void openShare()}
              disabled={!draft.leader && !entries.length}
            >
              {t("deck.share")}
            </button>
          </div>
          <div className="deck-toolbar-group deck-toolbar-view-group">
            <button
              type="button"
              className="deck-tool-details"
              onClick={onOpenDeckDetails}
              disabled={exporting}
            >
              {t("deck.details")}
            </button>
            <button
              type="button"
              className={`deck-tool-price${showPrices ? " active" : ""}`}
              onClick={() => setShowPrices((v) => !v)}
              disabled={!draft.leader && !entries.length}
            >
              {showPrices ? t("price.hide") : t("price.show")}
            </button>
          </div>
          <button
            type="button"
            className="deck-tool-danger"
            onClick={() => {
              draft.clearCards();
              setSaveChoice(false);
            }}
          >
            {t("deck.clear_draft")}
          </button>
        </div>

        {msg ? <p className="deck-msg">{msg}</p> : null}

        {(draft.leader || entries.length) && (structure.costCurve.length || structure.powerCurve.length || structure.counterCurve.length || structure.types.length) ? (
          <div className="deck-structure">
            {structure.costCurve.length || structure.powerCurve.length || structure.counterCurve.length ? (
              <div className="deck-structure-charts">
                <div
                  className="deck-structure-block"
                  style={{ ["--curve-share" as string]: Math.max(1, structure.costCurve.length) }}
                >
                  <strong>{t("deck.curve_cost")}</strong>
                  {structure.costCurve.length ? (
                    <div className="deck-curve-bars">
                      {structure.costCurve.map((b) => {
                        const max = Math.max(...structure.costCurve.map((x) => x.n), 1);
                        return (
                          <div key={`cost-${b.key}`} className="deck-curve-col" title={`${b.key}: ${b.n}`}>
                            <div className="deck-curve-bar" style={{ height: `${Math.max(8, (b.n / max) * 56)}px` }} />
                            <span className="deck-curve-n">{b.n}</span>
                            <span className="muted deck-curve-k">{b.key}</span>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <p className="muted deck-structure-line">—</p>
                  )}
                </div>
                <div
                  className="deck-structure-block"
                  style={{ ["--curve-share" as string]: Math.max(1, structure.powerCurve.length) }}
                >
                  <strong>{t("deck.curve_power")}</strong>
                  {structure.powerCurve.length ? (
                    <div className="deck-curve-bars">
                      {structure.powerCurve.map((b) => {
                        const max = Math.max(...structure.powerCurve.map((x) => x.n), 1);
                        return (
                          <div key={`power-${b.key}`} className="deck-curve-col" title={`${b.key}: ${b.n}`}>
                            <div
                              className="deck-curve-bar is-power"
                              style={{ height: `${Math.max(8, (b.n / max) * 56)}px` }}
                            />
                            <span className="deck-curve-n">{b.n}</span>
                            <span className="muted deck-curve-k">{b.key}</span>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <p className="muted deck-structure-line">—</p>
                  )}
                </div>
                <div
                  className="deck-structure-block"
                  style={{ ["--curve-share" as string]: Math.max(1, structure.counterCurve.length) }}
                >
                  <strong>{t("deck.curve_counter")}</strong>
                  {structure.counterCurve.length ? (
                    <div className="deck-curve-bars">
                      {structure.counterCurve.map((b) => {
                        const max = Math.max(...structure.counterCurve.map((x) => x.n), 1);
                        return (
                          <div key={`counter-${b.key}`} className="deck-curve-col" title={`${b.key}: ${b.n}`}>
                            <div
                              className="deck-curve-bar is-counter"
                              style={{ height: `${Math.max(8, (b.n / max) * 56)}px` }}
                            />
                            <span className="deck-curve-n">{b.n}</span>
                            <span className="muted deck-curve-k">{b.key}</span>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <p className="muted deck-structure-line">—</p>
                  )}
                </div>
              </div>
            ) : null}
            {structure.types.length ? (
              <div className="deck-structure-block">
                <strong>{t("deck.curve_types")}</strong>
                <p className="muted deck-structure-line">
                  {structure.types
                    .map((b) => `${localizeFilterToken("type", b.key, lang) || b.key} ${b.n}`)
                    .join(" · ")}
                </p>
              </div>
            ) : null}
          </div>
        ) : null}

        <h3 className="deck-list-heading">{t("deck.draft_list")}</h3>
        {showPrices ? (
          <p className="price-total-line">
            {pricesLoading
              ? t("price.loading")
              : t("price.total", {
                  total: formatYen(deckPriceSummary?.total ?? 0),
                  missing: String(deckPriceSummary?.missingCopies ?? 0),
                })}
          </p>
        ) : null}
        {!draft.leader && !entries.length ? (
          <p className="muted">{t("deck.draft_empty")}</p>
        ) : (
          <div className="draft-grid">
            {draft.leader ? (
              <div className="draft-tile leader" data-scroll-anchor={draft.leader}>
                <Link
                  href={`/cards/${encodeURIComponent(draft.leader)}?pickedVariant=${encodeURIComponent(draft.leader)}`}
                  className="draft-art"
                  title={t("wall.detail")}
                  scroll={false}
                  onPointerDown={() => flushCurrentScroll(draft.leader || undefined)}
                  onClick={() => flushCurrentScroll(draft.leader || undefined)}
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={cardImageUrl(draft.leader)} alt={draft.leader} />
                </Link>
                <div className="cap">{displayCardId(draft.leader)}</div>
                {showPrices ? (
                  <div className="price-chip">
                    {formatYen(unitPriceOf(priceMap, draft.leader))}
                  </div>
                ) : null}
                <div className="btns">
                  <button
                    type="button"
                    className="btn-remove"
                    onClick={() => draft.removeCard(draft.leader!, true)}
                  >
                    −1
                  </button>
                </div>
              </div>
            ) : null}
            {entries.map(([id, n]) => {
              const unit = unitPriceOf(priceMap, id);
              const line = unit == null ? null : unit * Number(n);
              return (
                <div key={id} className="draft-tile" data-scroll-anchor={id}>
                  <Link
                    href={`/cards/${encodeURIComponent(id)}?pickedVariant=${encodeURIComponent(id)}`}
                    className="draft-art"
                    title={t("wall.detail")}
                    scroll={false}
                    onPointerDown={() => flushCurrentScroll(id)}
                    onClick={() => flushCurrentScroll(id)}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={cardImageUrl(id)} alt={id} />
                  </Link>
                  <div className="cap">
                    {displayCardId(id)} ×{n}
                  </div>
                  {showPrices ? (
                    <div className="price-chip" title={unit != null ? `${formatYen(unit)} × ${n}` : undefined}>
                      {formatYen(line)}
                    </div>
                  ) : null}
                  <div className="btns">
                    <button type="button" className="btn-add" onClick={() => draft.addCard(id)}>
                      +1
                    </button>
                    <button type="button" className="btn-remove" onClick={() => draft.removeCard(id)}>
                      −1
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      <section className="deck-panel deck-search-wrap">
        <div className="deck-section-head">
          <div>
            <h2 className="deck-section-title">{t("deck.add_cards_title")}</h2>
            <p className="muted deck-section-sub">{t("deck.add_cards_sub")}</p>
          </div>
          <button type="button" className="secondary" onClick={() => setSectionAddOpen((v) => !v)}>
            {sectionAddOpen ? t("deck.section_collapse") : t("deck.section_expand")}
          </button>
        </div>
        {sectionAddOpen ? <SearchPageClient hideHeader /> : null}
      </section>

      {detailsOpen ? (
        <div
          className="deck-details-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeDeckDetails();
          }}
        >
          <section className="deck-details-modal" role="dialog" aria-modal="true" aria-labelledby="deck-details-title">
            <div className="deck-details-head">
              <h2 id="deck-details-title">{t("deck.details")}</h2>
              <button type="button" className="ghost" onClick={closeDeckDetails} aria-label={t("deck.close_detail")}>
                ×
              </button>
            </div>
            <div className="deck-details-preview">
              {previewUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={previewUrl} alt={previewTitle || t("deck.details")} />
              ) : (
                <div className="deck-details-loading">{t("deck.exporting")}</div>
              )}
            </div>
            <div className="deck-details-actions">
              <button type="button" onClick={onDownloadDeck} disabled={!previewBlob || exporting}>
                {exporting ? t("deck.exporting") : t("deck.download_image")}
              </button>
              <button type="button" className="secondary" onClick={closeDeckDetails}>
                {t("deck.close_detail")}
              </button>
            </div>
          </section>
        </div>
      ) : null}

      {shareOpen ? (
        <div
          className="deck-details-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setShareOpen(false);
          }}
        >
          <section className="deck-import-modal" role="dialog" aria-modal="true" aria-labelledby="deck-share-title">
            <div className="deck-details-head">
              <h2 id="deck-share-title">{t("deck.share")}</h2>
              <button type="button" className="ghost" onClick={() => setShareOpen(false)} aria-label={t("deck.close_detail")}>
                ×
              </button>
            </div>
            <p className="muted deck-import-hint">{t("deck.share_hint")}</p>
            {shareQr ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img className="deck-share-qr" src={shareQr} alt={t("deck.share_qr")} />
            ) : null}
            <input className="deck-share-url" readOnly value={shareUrl} onFocus={(e) => e.currentTarget.select()} />
            <div className="deck-details-actions">
              <button type="button" onClick={() => void copyShareLink()}>
                {t("deck.share_copy")}
              </button>
              <button type="button" className="secondary" onClick={() => setShareOpen(false)}>
                {t("deck.save_cancel")}
              </button>
            </div>
          </section>
        </div>
      ) : null}

      {importOpen ? (
        <div
          className="deck-details-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setImportOpen(false);
          }}
        >
          <section
            className="deck-import-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="deck-import-title"
          >
            <div className="deck-details-head">
              <h2 id="deck-import-title">{t("deck.import")}</h2>
              <button
                type="button"
                className="ghost"
                onClick={() => setImportOpen(false)}
                aria-label={t("deck.close_detail")}
              >
                ×
              </button>
            </div>
            <p className="muted deck-import-hint">{t("deck.import_hint")}</p>
            <textarea
              className="deck-import-textarea"
              value={importText}
              onChange={(e) => setImportText(e.target.value)}
              placeholder={t("deck.import_ph")}
              rows={12}
              autoFocus
            />
            <div className="deck-details-actions">
              <button
                type="button"
                onClick={onApplyImport}
                disabled={!importText.trim() || importing}
              >
                {importing ? t("deck.importing") : t("deck.import_apply")}
              </button>
              <button type="button" className="secondary" onClick={() => setImportOpen(false)}>
                {t("deck.save_cancel")}
              </button>
            </div>
          </section>
        </div>
      ) : null}

      {copyText ? (
        <div
          className="deck-details-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setCopyText("");
          }}
        >
          <section
            className="deck-import-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="deck-copy-title"
          >
            <div className="deck-details-head">
              <h2 id="deck-copy-title">{t("deck.copy_list")}</h2>
              <button
                type="button"
                className="ghost"
                onClick={() => setCopyText("")}
                aria-label={t("deck.close_detail")}
              >
                ×
              </button>
            </div>
            <p className="muted deck-import-hint">{t("deck.copy_manual_hint")}</p>
            <textarea
              className="deck-import-textarea"
              value={copyText}
              readOnly
              rows={12}
              onFocus={(e) => e.currentTarget.select()}
              autoFocus
            />
            <div className="deck-details-actions">
              <button type="button" className="secondary" onClick={() => setCopyText("")}>
                {t("deck.close_detail")}
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
