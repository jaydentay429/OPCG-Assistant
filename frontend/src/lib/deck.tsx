"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { normalizeCardId } from "./cardId";
import { clampDeckCopies, maxCopiesForCard } from "./deckLimits";

const STORAGE_KEY = "opcg_deck_draft_v1";

type DeckDraft = {
  leader: string | null;
  cards: Record<string, number>;
  editingId: string | null;
  name: string;
};

type DeckCtx = DeckDraft & {
  nonLeaderTotal: number;
  ready: boolean;
  setName: (n: string) => void;
  setEditingId: (id: string | null) => void;
  clearDraft: () => void;
  /** Clear leader/cards but keep editing target + name (rebuild in place). */
  clearCards: () => void;
  loadDeck: (opts: {
    id: string;
    name: string;
    leader_card_id?: string | null;
    cards?: Record<string, number>;
  }) => void;
  /** Load a shared/imported deck as a new draft (does not attach to a saved deck id). */
  importDeck: (opts: {
    name?: string;
    leader?: string | null;
    cards?: Record<string, number>;
  }) => void;
  /** Merge pasted cards into the current draft (keeps name / editingId). */
  mergeIntoDeck: (opts: {
    name?: string;
    leader?: string | null;
    cards?: Record<string, number>;
  }) => { added: number; skipped: number };
  addCard: (cardId: string, cardType?: string | null) => { ok: boolean; msg?: string };
  removeCard: (cardId: string, asLeader?: boolean) => { ok: boolean; msg?: string };
  qtyOf: (cardId: string) => number;
};

const Ctx = createContext<DeckCtx | null>(null);

const empty: DeckDraft = { leader: null, cards: {}, editingId: null, name: "" };

export function isLeaderType(cardType?: string | null) {
  const t = String(cardType || "").toLowerCase();
  return t.includes("leader") || t.includes("领袖") || t.includes("領袖");
}

function sanitizeDraft(raw: unknown): DeckDraft {
  if (!raw || typeof raw !== "object") return empty;
  const o = raw as Partial<DeckDraft>;
  const cards: Record<string, number> = {};
  if (o.cards && typeof o.cards === "object") {
    for (const [k, v] of Object.entries(o.cards)) {
      const id = normalizeCardId(k);
      const n = Number(v) || 0;
      if (id && n > 0) cards[id] = clampDeckCopies(id, Math.floor(n));
    }
  }
  return {
    leader: o.leader ? normalizeCardId(String(o.leader)) || null : null,
    cards,
    editingId: typeof o.editingId === "string" && o.editingId ? o.editingId : null,
    name: typeof o.name === "string" ? o.name : "",
  };
}

function readStoredDraft(): DeckDraft {
  if (typeof window === "undefined") return empty;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return empty;
    return sanitizeDraft(JSON.parse(raw));
  } catch {
    return empty;
  }
}

export function DeckProvider({ children }: { children: ReactNode }) {
  const [draft, setDraft] = useState<DeckDraft>(empty);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setDraft(readStoredDraft());
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(draft));
    } catch {
      /* ignore quota */
    }
  }, [draft, ready]);

  const nonLeaderTotal = useMemo(
    () => Object.values(draft.cards).reduce((a, b) => a + (Number(b) || 0), 0),
    [draft.cards],
  );

  const setName = useCallback((n: string) => setDraft((d) => ({ ...d, name: n })), []);
  const setEditingId = useCallback(
    (id: string | null) => setDraft((d) => ({ ...d, editingId: id })),
    [],
  );

  const clearDraft = useCallback(() => setDraft(empty), []);

  const clearCards = useCallback(
    () => setDraft((d) => ({ ...d, leader: null, cards: {} })),
    [],
  );

  const loadDeck = useCallback(
    (opts: {
      id: string;
      name: string;
      leader_card_id?: string | null;
      cards?: Record<string, number>;
    }) => {
      setDraft({
        editingId: opts.id,
        name: opts.name || "",
        leader: opts.leader_card_id ? normalizeCardId(opts.leader_card_id) : null,
        cards: Object.fromEntries(
          Object.entries(opts.cards || {}).map(([k, v]) => [normalizeCardId(k), Number(v) || 0]),
        ),
      });
    },
    [],
  );

  const importDeck = useCallback(
    (opts: { name?: string; leader?: string | null; cards?: Record<string, number> }) => {
      const cards: Record<string, number> = {};
      for (const [k, v] of Object.entries(opts.cards || {})) {
        const id = normalizeCardId(k);
        const n = Math.floor(Number(v) || 0);
        if (id && n > 0) cards[id] = clampDeckCopies(id, n);
      }
      setDraft({
        editingId: null,
        name: typeof opts.name === "string" ? opts.name : "",
        leader: opts.leader ? normalizeCardId(opts.leader) || null : null,
        cards,
      });
    },
    [],
  );

  /** Merge pasted cards into the current draft (keeps name / editingId). */
  const mergeIntoDeck = useCallback(
    (opts: { name?: string; leader?: string | null; cards?: Record<string, number> }) => {
      let summary = { added: 0, skipped: 0 };
      setDraft((d) => {
        const cards = { ...d.cards };
        let total = Object.values(cards).reduce((a, b) => a + (Number(b) || 0), 0);
        let added = 0;
        let skipped = 0;
        for (const [k, v] of Object.entries(opts.cards || {})) {
          const id = normalizeCardId(k);
          let need = Math.floor(Number(v) || 0);
          if (!id || need <= 0) continue;
          while (need > 0) {
            const cur = Number(cards[id] || 0);
            const maxCopies = maxCopiesForCard(id);
            if (cur >= maxCopies || total >= 50) {
              skipped += need;
              break;
            }
            cards[id] = cur + 1;
            total += 1;
            need -= 1;
            added += 1;
          }
        }
        summary = { added, skipped };
        const nextLeader =
          d.leader || (opts.leader ? normalizeCardId(opts.leader) || null : null);
        const nextName =
          d.name.trim() || (typeof opts.name === "string" ? opts.name.trim() : "") || d.name;
        return { ...d, leader: nextLeader, name: nextName, cards };
      });
      return summary;
    },
    [],
  );

  const addCard = useCallback((cardId: string, cardType?: string | null) => {
    const id = normalizeCardId(cardId);
    if (!id) return { ok: false, msg: "invalid id" };
    let result: { ok: boolean; msg?: string } = { ok: true };
    setDraft((d) => {
      if (isLeaderType(cardType)) {
        return { ...d, leader: id };
      }
      const cur = Number(d.cards[id] || 0);
      const maxCopies = maxCopiesForCard(id);
      if (cur >= maxCopies) {
        result = { ok: false, msg: maxCopies >= 50 ? "deck full for this card" : "max 4 copies" };
        return d;
      }
      const total = Object.values(d.cards).reduce((a, b) => a + (Number(b) || 0), 0);
      if (total >= 50) {
        result = { ok: false, msg: "deck full (50)" };
        return d;
      }
      return { ...d, cards: { ...d.cards, [id]: cur + 1 } };
    });
    return result;
  }, []);

  const removeCard = useCallback((cardId: string, asLeader = false) => {
    const id = normalizeCardId(cardId);
    setDraft((d) => {
      if (asLeader || d.leader === id) {
        return { ...d, leader: d.leader === id ? null : d.leader };
      }
      const cur = Number(d.cards[id] || 0);
      if (cur <= 1) {
        const next = { ...d.cards };
        delete next[id];
        return { ...d, cards: next };
      }
      return { ...d, cards: { ...d.cards, [id]: cur - 1 } };
    });
    return { ok: true };
  }, []);

  const qtyOf = useCallback(
    (cardId: string) => {
      const id = normalizeCardId(cardId);
      if (!id) return 0;
      if (draft.leader === id) return 1;
      return Number(draft.cards[id] || 0);
    },
    [draft.leader, draft.cards],
  );

  const value = useMemo(
    () => ({
      ...draft,
      nonLeaderTotal,
      ready,
      setName,
      setEditingId,
      clearDraft,
      clearCards,
      loadDeck,
      importDeck,
      mergeIntoDeck,
      addCard,
      removeCard,
      qtyOf,
    }),
    [
      draft,
      nonLeaderTotal,
      ready,
      setName,
      setEditingId,
      clearDraft,
      clearCards,
      loadDeck,
      importDeck,
      mergeIntoDeck,
      addCard,
      removeCard,
      qtyOf,
    ],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useDeck() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useDeck outside provider");
  return ctx;
}

/** Display name for the draft currently receiving +1/−1. */
export function useDeckTargetLabel(unnamed: string, newDraft: string): string {
  const deck = useDeck();
  const name = deck.name.trim();
  if (deck.editingId) return name || unnamed;
  if (name) return name;
  return newDraft;
}
