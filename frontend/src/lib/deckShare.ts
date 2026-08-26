import { normalizeCardId } from "@/lib/cardId";
import { clampDeckCopies } from "@/lib/deckLimits";

export type SharedDeck = {
  name: string;
  leader: string | null;
  cards: Record<string, number>;
};

const SHARE_SITE = "https://optcgassistant.com";

function shareSiteBase(): string {
  if (typeof window !== "undefined") {
    const host = window.location.hostname;
    if (host === "localhost" || host === "127.0.0.1") return window.location.origin;
  }
  return SHARE_SITE;
}

function toBase64Url(bytes: Uint8Array): string {
  let bin = "";
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]!);
  const b64 = btoa(bin);
  return b64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function fromBase64Url(text: string): Uint8Array | null {
  try {
    const padded = text.replace(/-/g, "+").replace(/_/g, "/");
    const pad = padded.length % 4 === 0 ? "" : "=".repeat(4 - (padded.length % 4));
    const bin = atob(padded + pad);
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  } catch {
    return null;
  }
}

function sanitizeShared(raw: unknown): SharedDeck | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;
  const cards: Record<string, number> = {};
  const src =
    o.c && typeof o.c === "object"
      ? (o.c as Record<string, unknown>)
      : o.cards && typeof o.cards === "object"
        ? (o.cards as Record<string, unknown>)
        : null;
  if (src) {
    for (const [k, v] of Object.entries(src)) {
      const id = normalizeCardId(k);
      const n = Math.floor(Number(v) || 0);
      if (id && n > 0) cards[id] = clampDeckCopies(id, n);
    }
  }
  const leaderRaw = o.l ?? o.leader;
  const leader = leaderRaw ? normalizeCardId(String(leaderRaw)) || null : null;
  const name = typeof o.n === "string" ? o.n : typeof o.name === "string" ? o.name : "";
  if (!leader && !Object.keys(cards).length) return null;
  return { name, leader, cards };
}

/** Compact payload: {"v":1,"n":"...","l":"OP15-002","c":{"ST01-015":4}} */
export function encodeDeckSharePayload(deck: SharedDeck): string {
  const c: Record<string, number> = {};
  for (const [k, v] of Object.entries(deck.cards || {})) {
    const id = normalizeCardId(k);
    const n = Math.floor(Number(v) || 0);
    if (id && n > 0) c[id] = clampDeckCopies(id, n);
  }
  const payload: Record<string, unknown> = { v: 1, c };
  const name = (deck.name || "").trim().slice(0, 80);
  if (name) payload.n = name;
  const leader = deck.leader ? normalizeCardId(deck.leader) : "";
  if (leader) payload.l = leader;
  const json = JSON.stringify(payload);
  return toBase64Url(new TextEncoder().encode(json));
}

export function decodeDeckSharePayload(raw: string): SharedDeck | null {
  const text = String(raw || "").trim();
  if (!text) return null;
  const bytes = fromBase64Url(text);
  if (!bytes) return null;
  try {
    const json = new TextDecoder().decode(bytes);
    return sanitizeShared(JSON.parse(json));
  } catch {
    return null;
  }
}

export function buildDeckShareUrl(deck: SharedDeck, siteBase?: string): string {
  const base = String(siteBase || shareSiteBase()).replace(/\/+$/, "");
  const d = encodeDeckSharePayload(deck);
  return `${base}/builder?d=${d}`;
}

/** Standard ids pack to letters + 5 digits, e.g. OP01-006 -> OP01006. */
const PACKABLE_ID_RE = /^([A-Z]{2,4}\d{2})-(\d{3})$/;
/** Packed stream token: letters + 5 id digits + 1 qty digit. */
const PACKED_TOKEN_RE = /([A-Z]{2,4})(\d{5})(\d)/g;

function packCardId(id: string): string | null {
  const m = PACKABLE_ID_RE.exec(normalizeCardId(id));
  return m ? `${m[1]}${m[2]}` : null;
}

function unpackCardId(letters: string, digits: string): string {
  return `${letters}${digits.slice(0, 2)}-${digits.slice(2)}`;
}

function maybeUnpackId(id: string): string | null {
  const m = /^([A-Z]{2,4})(\d{5})$/.exec(id.toUpperCase());
  return (m ? normalizeCardId(unpackCardId(m[1]!, m[2]!)) : normalizeCardId(id)) || null;
}

/**
 * Plain-text share link with dash-free ids and no separators, so the QR code
 * stays around 49x49 modules instead of 61x61. Variants and other odd ids
 * fall back to a comma list in `x`. The deck name is omitted by default since
 * it is already printed on the deck image.
 */
export function buildDeckShareUrlCompact(
  deck: SharedDeck,
  siteBase?: string,
  opts?: { includeName?: boolean; maxNameLength?: number },
): string {
  const base = String(siteBase || shareSiteBase()).replace(/\/+$/, "");
  const parts: string[] = [];

  const leader = deck.leader ? normalizeCardId(deck.leader) : "";
  if (leader) parts.push(`l=${packCardId(leader) || leader}`);

  const packed: string[] = [];
  const extra: string[] = [];
  for (const [rawId, rawQty] of Object.entries(deck.cards || {})) {
    const id = normalizeCardId(rawId);
    const n = clampDeckCopies(id, Math.floor(Number(rawQty) || 0));
    if (!id || n <= 0) continue;
    const short = packCardId(id);
    // Packed stream only stores a single digit qty (1–9); larger stacks use x=.
    if (short && n <= 9) packed.push(`${short}${n}`);
    else extra.push(`${id}.${n}`);
  }
  if (packed.length) parts.push(`c=${packed.join("")}`);
  if (extra.length) parts.push(`x=${extra.join(",")}`);

  if (opts?.includeName) {
    const name = (deck.name || "").trim().slice(0, opts.maxNameLength ?? 24);
    if (name) parts.push(`n=${encodeURIComponent(name)}`);
  }
  return `${base}/builder?${parts.join("&")}`;
}

/** Read share payload from current location (?d=... or legacy n/l/c). */
export function parseDeckShareFromSearch(search: string): SharedDeck | null {
  const q = search.startsWith("?") ? search.slice(1) : search;
  const sp = new URLSearchParams(q);
  const d = sp.get("d") || sp.get("deck");
  if (d) return decodeDeckSharePayload(d);

  // Query form: ?n=&l=&c=... where c is either the packed stream (OP010064...)
  // or the older ID.qty,ID.qty list. Odd ids always live in x= as a list.
  const rawLeader = sp.get("l");
  const leader = rawLeader ? maybeUnpackId(normalizeCardId(rawLeader) || rawLeader) : null;
  const name = sp.get("n") || "";
  const cards: Record<string, number> = {};

  const addList = (text: string) => {
    for (const part of text.split(/[,;]+/)) {
      const m = part.trim().match(/^([A-Za-z0-9-]+)[.*x×](\d+)$/i);
      if (!m) continue;
      const id = normalizeCardId(m[1]!);
      const n = clampDeckCopies(id, Math.floor(Number(m[2]) || 0));
      if (id && n > 0) cards[id] = n;
    }
  };

  const c = sp.get("c") || "";
  if (/[,;.*x×]/i.test(c)) {
    addList(c);
  } else if (c) {
    PACKED_TOKEN_RE.lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = PACKED_TOKEN_RE.exec(c.toUpperCase()))) {
      const id = normalizeCardId(unpackCardId(m[1]!, m[2]!));
      const n = clampDeckCopies(id, Number(m[3]));
      if (id && n > 0) cards[id] = n;
    }
  }
  addList(sp.get("x") || "");

  if (!leader && !Object.keys(cards).length) return null;
  return { name, leader, cards };
}

const CARD_ID_TOKEN = String.raw`[A-Za-z]{1,4}\d{0,2}-\d{3}(?:-[A-Za-z0-9]+)?`;
const LINE_QTY_AFTER = new RegExp(
  `^(${CARD_ID_TOKEN})\\s*(?:[x×*]\\s*|\\s+)(\\d{1,2})\\s*$`,
  "i",
);
const LINE_QTY_BEFORE = new RegExp(
  `^(\\d{1,2})\\s*[x×*]\\s*(${CARD_ID_TOKEN})\\s*$`,
  "i",
);
const LINE_ID_ONLY = new RegExp(`^(${CARD_ID_TOKEN})\\s*$`, "i");
const LINE_LEADER = new RegExp(
  `^(?:leader|领袖|領袖|l)\\s*[:：]\\s*(${CARD_ID_TOKEN})\\s*(?:[x×*]\\s*1)?\\s*$`,
  "i",
);

function addQty(cards: Record<string, number>, id: string, qty: number) {
  const n = Math.floor(qty);
  if (!id || n <= 0) return;
  cards[id] = clampDeckCopies(id, (cards[id] || 0) + n);
}

/**
 * Parse a pasted deck list. Accepts the format produced by "Copy IDs & qty"
 * (`OP15-002 x1` then `ST01-015 x4`), `4xOP01-006`, plain ids, `Leader: …`,
 * share URLs, and packed `?l=&c=` query strings.
 */
export function parseDeckListText(raw: string): SharedDeck | null {
  const text = String(raw || "").trim();
  if (!text) return null;

  // Full share URL or query string.
  const urlMatch = text.match(/https?:\/\/[^\s]+/i);
  if (urlMatch) {
    try {
      const u = new URL(urlMatch[0]!);
      const fromUrl = parseDeckShareFromSearch(u.search);
      if (fromUrl) return fromUrl;
    } catch {
      /* fall through */
    }
  }
  if (/[?&](?:d|deck|l|c)=/.test(text)) {
    const q = text.includes("?") ? text.slice(text.indexOf("?")) : `?${text}`;
    const fromQuery = parseDeckShareFromSearch(q);
    if (fromQuery) return fromQuery;
  }

  const cards: Record<string, number> = {};
  let leader: string | null = null;
  let name = "";

  const lines = text
    .split(/[\r\n]+/)
    .flatMap((line) => line.split(/[,;|]+/))
    .map((line) => line.trim())
    .filter(Boolean);

  for (const line of lines) {
    const nameMatch = line.match(/^(?:name|卡组名|卡組名|デッキ名)\s*[:：]\s*(.+)$/i);
    if (nameMatch) {
      name = nameMatch[1]!.trim().slice(0, 80);
      continue;
    }

    const leaderMatch = LINE_LEADER.exec(line);
    if (leaderMatch) {
      leader = normalizeCardId(leaderMatch[1]!);
      continue;
    }

    let id = "";
    let qty = 0;
    const after = LINE_QTY_AFTER.exec(line);
    if (after) {
      id = normalizeCardId(after[1]!);
      qty = Number(after[2]);
    } else {
      const before = LINE_QTY_BEFORE.exec(line);
      if (before) {
        qty = Number(before[1]);
        id = normalizeCardId(before[2]!);
      } else {
        const only = LINE_ID_ONLY.exec(line);
        if (only) {
          id = normalizeCardId(only[1]!);
          qty = 1;
        }
      }
    }
    if (!id || qty <= 0) continue;
    addQty(cards, id, qty);
  }

  if (!leader && !Object.keys(cards).length) return null;
  return { name, leader, cards };
}
