import QRCode from "qrcode";
import { API_BASE, cardImagePacksUrl, cardImageUrl, fetchDeckStatsBatch, type DeckStatFields } from "@/lib/api";
import { cardIdSortKey, displayCardId, normalizeCardId } from "@/lib/cardId";
import { localizeCardName } from "@/lib/cardLocale";
import type { Lang } from "@/lib/i18n";
import { buildDeckShareUrlCompact } from "@/lib/deckShare";
import {
  costBucketKey,
  counterBucketKey,
  orderedCounterKeys,
  orderedPowerKeys,
  powerBucketKey,
} from "@/lib/deckStructure";

const SITE_HOST_LABEL = "optcgassistant.com";

/** Instagram Feed 4:5. Drawn at 2× then scaled down for a sharp 1080×1350 PNG. */
const OUT_W = 1080;
const OUT_H = 1350;
const SCALE = 2;

function isCoarseMobile(): boolean {
  if (typeof window === "undefined") return false;
  return Boolean(
    window.matchMedia?.("(max-width: 640px)")?.matches ||
      window.matchMedia?.("(pointer: coarse)")?.matches,
  );
}

function canvasToBlob(canvas: HTMLCanvasElement, type = "image/png", quality?: number): Promise<Blob | null> {
  return new Promise((resolve) => {
    try {
      canvas.toBlob((blob) => resolve(blob), type, quality);
    } catch {
      try {
        const dataUrl = canvas.toDataURL(type, quality);
        const comma = dataUrl.indexOf(",");
        if (comma < 0) {
          resolve(null);
          return;
        }
        const bin = atob(dataUrl.slice(comma + 1));
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        resolve(new Blob([bytes], { type }));
      } catch {
        resolve(null);
      }
    }
  });
}

async function blobToDrawable(blob: Blob): Promise<CanvasImageSource | null> {
  const mobile = isCoarseMobile();
  const resize = mobile
    ? ({ resizeWidth: 220, resizeHeight: 308, resizeQuality: "medium" } as const)
    : ({ resizeWidth: 366, resizeHeight: 512, resizeQuality: "high" } as const);

  if (typeof createImageBitmap === "function") {
    try {
      return await createImageBitmap(blob, resize);
    } catch {
      try {
        return await createImageBitmap(blob);
      } catch {
        /* fall through */
      }
    }
  }

  try {
    const url = URL.createObjectURL(blob);
    try {
      const img = await new Promise<HTMLImageElement>((resolve, reject) => {
        const el = new Image();
        el.onload = () => resolve(el);
        el.onerror = () => reject(new Error("img decode failed"));
        el.src = url;
      });
      return img;
    } finally {
      URL.revokeObjectURL(url);
    }
  } catch {
    return null;
  }
}

async function fetchDrawable(url: string): Promise<CanvasImageSource | null> {
  try {
    const res = await fetch(url, { mode: "cors", credentials: "omit", cache: "force-cache" });
    if (!res.ok) return null;
    const blob = await res.blob();
    if (!blob || blob.size < 32) return null;
    return await blobToDrawable(blob);
  } catch {
    return null;
  }
}

async function loadCardDrawable(cardId: string): Promise<CanvasImageSource | null> {
  // Prefer API packs/proxy (CORS). CDN often lacks ACAO for fetch().
  const primary = await fetchDrawable(cardImagePacksUrl(cardId));
  if (primary) return primary;
  return fetchDrawable(cardImageUrl(cardId));
}

const COLOR_DOT: Record<string, string> = {
  red: "#ef4444",
  紅: "#ef4444",
  红: "#ef4444",
  green: "#22c55e",
  綠: "#22c55e",
  绿: "#22c55e",
  blue: "#3b82f6",
  藍: "#3b82f6",
  蓝: "#3b82f6",
  purple: "#a855f7",
  紫: "#a855f7",
  black: "#0f172a",
  黑: "#0f172a",
  yellow: "#eab308",
  黃: "#eab308",
  黄: "#eab308",
};

const TYPE_ORDER = ["Character", "Event", "Stage"] as const;

export type DeckExportLabels = {
  title: string;
  leader: string;
  noLeader: string;
  cardsN: string;
  uniqueN: string;
  costCurve: string;
  powerCurve: string;
  counterCurve: string;
  createdBy: string;
  qty: string;
};

type ExportInput = {
  name: string;
  leader: string | null;
  cards: Record<string, number>;
  lang: Lang;
  labels: DeckExportLabels;
  includeQr?: boolean;
  /** Optional meta line drawn beside the leader art (e.g. tournament info). */
  subtitle?: string;
};

type GridCard = { id: string; n: number; cost: number; type: string; name: string };

const TYPE_ACCENT: Record<string, string> = {
  Character: "#38bdf8",
  Event: "#c084fc",
  Stage: "#fbbf24",
};

function toInt(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

async function mapPool<T, R>(items: T[], concurrency: number, fn: (item: T) => Promise<R>): Promise<R[]> {
  const out: R[] = new Array(items.length);
  let i = 0;
  async function worker() {
    while (i < items.length) {
      const idx = i++;
      out[idx] = await fn(items[idx]);
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, Math.max(1, items.length)) }, () => worker()));
  return out;
}

function roundRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
) {
  const rr = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + rr, y);
  ctx.arcTo(x + w, y, x + w, y + h, rr);
  ctx.arcTo(x + w, y + h, x, y + h, rr);
  ctx.arcTo(x, y + h, x, y, rr);
  ctx.arcTo(x, y, x + w, y, rr);
  ctx.closePath();
}

function drawBarChart(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  title: string,
  color: string,
  keys: string[],
  bucket: Record<string, number>,
) {
  ctx.fillStyle = color;
  ctx.font = "800 34px system-ui, sans-serif";
  ctx.textAlign = "left";
  if (ctx.measureText(title).width > w - 8) {
    ctx.font = "800 26px system-ui, sans-serif";
  }
  ctx.fillText(title, x, y + 32);

  const shown = keys.filter((k) => (bucket[k] || 0) > 0);
  const useKeys = shown.length ? shown : keys;
  const maxN = Math.max(1, ...useKeys.map((k) => bucket[k] || 0));
  const titleH = 48;
  const valueH = 36;
  const labelH = 42;
  const barAreaY = y + titleH + valueH;
  const barAreaH = Math.max(40, h - titleH - valueH - labelH);
  const slotW = w / Math.max(1, useKeys.length);
  const barW = Math.max(22, Math.min(52, slotW * 0.58));
  useKeys.forEach((key, i) => {
    const n = bucket[key] || 0;
    const bh = Math.max(20, Math.round((n / maxN) * barAreaH));
    const bx = x + i * slotW + (slotW - barW) / 2;
    const by = barAreaY + barAreaH - bh;
    roundRect(ctx, bx, by, barW, bh, 10);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.fillStyle = "#f8fafc";
    ctx.font = "800 28px system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(String(n), bx + barW / 2, barAreaY - 10);
    ctx.fillStyle = "#cbd5e1";
    ctx.font = "800 26px system-ui, sans-serif";
    ctx.fillText(key, bx + barW / 2, barAreaY + barAreaH + 34);
    ctx.textAlign = "left";
  });
}

function typeKey(raw: string | null | undefined): string {
  const t = String(raw || "").trim();
  if (/leader|领袖|領袖/i.test(t)) return "Leader";
  if (/character|角色/i.test(t)) return "Character";
  if (/event|事件/i.test(t)) return "Event";
  if (/stage|舞台|场地|場地/i.test(t)) return "Stage";
  return t || "?";
}

function drawCover(
  ctx: CanvasRenderingContext2D,
  img: CanvasImageSource,
  x: number,
  y: number,
  w: number,
  h: number,
) {
  const iw = Number((img as ImageBitmap).width || (img as HTMLImageElement).naturalWidth || 1);
  const ih = Number((img as ImageBitmap).height || (img as HTMLImageElement).naturalHeight || 1);
  const scale = Math.max(w / Math.max(1, iw), h / Math.max(1, ih));
  const dw = iw * scale;
  const dh = ih * scale;
  ctx.drawImage(img, x + (w - dw) / 2, y + (h - dh) / 2, dw, dh);
}

/** Fill the slot from the top of the card; clip the bottom if the cell is too short. */
function drawFromTop(
  ctx: CanvasRenderingContext2D,
  img: CanvasImageSource,
  x: number,
  y: number,
  w: number,
  h: number,
) {
  const iw = Number((img as ImageBitmap).width || (img as HTMLImageElement).naturalWidth || 1);
  const ih = Number((img as ImageBitmap).height || (img as HTMLImageElement).naturalHeight || 1);
  const scale = w / Math.max(1, iw);
  ctx.drawImage(img, x, y, w, ih * scale);
}

function fitText(ctx: CanvasRenderingContext2D, text: string, maxW: number): string {
  if (ctx.measureText(text).width <= maxW) return text;
  let s = text;
  while (s.length > 1 && ctx.measureText(`${s}…`).width > maxW) s = s.slice(0, -1);
  return `${s}…`;
}

function wrapLines(ctx: CanvasRenderingContext2D, text: string, maxW: number, maxLines: number): string[] {
  const raw = String(text || "").trim();
  if (!raw) return [];
  if (ctx.measureText(raw).width <= maxW) return [raw];
  const lines: string[] = [];
  let cur = "";
  const chars = [...raw];
  for (let i = 0; i < chars.length; i++) {
    const ch = chars[i];
    const next = cur + ch;
    if (!cur || ctx.measureText(next).width <= maxW) {
      cur = next;
      continue;
    }
    if (lines.length >= maxLines - 1) {
      lines.push(fitText(ctx, cur + chars.slice(i).join(""), maxW));
      return lines;
    }
    lines.push(cur);
    cur = ch;
  }
  if (cur) lines.push(cur);
  return lines.slice(0, maxLines);
}

function colorDotFill(raw: string): string {
  const key = String(raw || "").trim();
  return COLOR_DOT[key] || COLOR_DOT[key.toLowerCase()] || "#94a3b8";
}

function uniqueColors(raw: string[] | undefined): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const c of raw || []) {
    const fill = colorDotFill(c);
    if (seen.has(fill)) continue;
    seen.add(fill);
    out.push(c);
  }
  return out;
}

function leaderDisplayName(st: DeckStatFields | undefined, lang: Lang, fallback: string): string {
  if (!st) return fallback;
  return localizeCardName(st.name, st.name_en, lang) || fallback;
}

function downsample(src: HTMLCanvasElement, width: number, height: number): HTMLCanvasElement {
  const out = document.createElement("canvas");
  out.width = width;
  out.height = height;
  const ctx = out.getContext("2d");
  if (!ctx) return src;
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(src, 0, 0, width, height);
  return out;
}

async function renderDeckCanvas(input: ExportInput): Promise<{ blob: Blob; title: string; width: number; height: number }> {
  const leaderId = input.leader ? normalizeCardId(input.leader) : "";
  const entries = Object.entries(input.cards)
    .map(([id, n]) => [normalizeCardId(id), Math.max(0, Math.floor(Number(n) || 0))] as const)
    .filter(([id, n]) => id && n > 0);

  const allIds = [...(leaderId ? [leaderId] : []), ...entries.map(([id]) => id)];
  const statsMap = await fetchDeckStatsBatch(allIds);

  const images = new Map<string, CanvasImageSource | null>();
  const poolSize = isCoarseMobile() ? 2 : 4;
  await mapPool(allIds, poolSize, async (id) => {
    images.set(id, await loadCardDrawable(id));
    return id;
  });

  const costBucket: Record<string, number> = {};
  const powerBucket: Record<string, number> = {};
  const counterBucket: Record<string, number> = {};
  const bump = (map: Record<string, number>, key: string, n: number) => {
    map[key] = (map[key] || 0) + n;
  };

  const gridCards: GridCard[] = [];
  for (const [id, n] of entries) {
    const st: DeckStatFields = statsMap[id] || {};
    const cost = toInt(st.cost);
    const costKey = costBucketKey(cost, st.card_type);
    bump(costBucket, costKey, n);
    const powerKey = powerBucketKey(toInt(st.power), st.card_type);
    if (powerKey) bump(powerBucket, powerKey, n);
    const counterKey = counterBucketKey(toInt(st.counter), st.card_type);
    if (counterKey) bump(counterBucket, counterKey, n);
    const tk = typeKey(st.card_type);
    const sortCost = costKey === "?" ? 99 : Number(costKey);
    gridCards.push({
      id,
      n,
      cost: sortCost,
      type: tk,
      name: leaderDisplayName(st, input.lang, displayCardId(id)),
    });
  }

  const costKeys: string[] = [];
  for (let c = 0; c <= 10; c++) {
    if (costBucket[String(c)]) costKeys.push(String(c));
  }
  if (costBucket["?"]) costKeys.push("?");

  const powerKeys = orderedPowerKeys(powerBucket);
  const counterKeys = orderedCounterKeys(counterBucket);

  const packed: GridCard[] = [];
  for (const key of TYPE_ORDER) {
    packed.push(
      ...gridCards
        .filter((c) => c.type === key)
        .sort((a, b) => a.cost - b.cost || cardIdSortKey(a.id).localeCompare(cardIdSortKey(b.id))),
    );
  }
  packed.push(
    ...gridCards
      .filter((c) => !TYPE_ORDER.includes(c.type as (typeof TYPE_ORDER)[number]))
      .sort((a, b) => a.cost - b.cost || cardIdSortKey(a.id).localeCompare(cardIdSortKey(b.id))),
  );

  const title = input.name.trim() || input.labels.title;
  const leaderSt = leaderId ? statsMap[leaderId] : undefined;
  const leaderName = leaderId
    ? leaderDisplayName(leaderSt, input.lang, displayCardId(leaderId))
    : input.labels.noLeader;
  const leaderColors = uniqueColors(leaderSt?.colors);

  const includeQr = input.includeQr !== false;
  const shareUrl = includeQr
    ? buildDeckShareUrlCompact({
        name: title,
        leader: leaderId || null,
        cards: Object.fromEntries(entries),
      })
    : "";
  let qrCanvas: HTMLCanvasElement | null = null;
  const qrDraw = 176;
  if (shareUrl) {
    try {
      const c = document.createElement("canvas");
      await QRCode.toCanvas(c, shareUrl, {
        width: qrDraw,
        margin: 1,
        color: { dark: "#000000", light: "#ffffff" },
        errorCorrectionLevel: "M",
      });
      qrCanvas = c;
    } catch {
      qrCanvas = null;
    }
  }

  const W = OUT_W * SCALE;
  const H = OUT_H * SCALE;
  const pad = 48;
  const heroH = 392;
  const structH = 308;
  const footerH = 188;
  const sectionGap = 20;

  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d", { alpha: false });
  if (!ctx) throw new Error("canvas unsupported");

  ctx.fillStyle = "#0b1220";
  ctx.fillRect(0, 0, W, H);

  const leaderImg = leaderId ? images.get(leaderId) : null;
  const heroBg = ctx.createLinearGradient(0, 0, W, heroH);
  heroBg.addColorStop(0, "#152033");
  heroBg.addColorStop(1, "#0b1220");
  ctx.fillStyle = heroBg;
  ctx.fillRect(0, 0, W, heroH);

  const portraitH = heroH - 48;
  const portraitW = Math.round(portraitH / 1.4);
  const portraitX = pad;
  const portraitY = 24;
  if (leaderImg) {
    roundRect(ctx, portraitX, portraitY, portraitW, portraitH, 22);
    ctx.fillStyle = "#020617";
    ctx.fill();
    ctx.save();
    roundRect(ctx, portraitX, portraitY, portraitW, portraitH, 22);
    ctx.clip();
    drawCover(ctx, leaderImg, portraitX, portraitY, portraitW, portraitH);
    ctx.restore();
    ctx.strokeStyle = "rgba(251, 191, 36, 0.85)";
    ctx.lineWidth = 4;
    roundRect(ctx, portraitX, portraitY, portraitW, portraitH, 22);
    ctx.stroke();
  }

  const textX = leaderImg ? portraitX + portraitW + 36 : pad;
  const textW = W - pad - textX;
  ctx.fillStyle = "#f8fafc";
  ctx.font = "800 64px system-ui, sans-serif";
  ctx.textAlign = "left";
  const titleLines = wrapLines(ctx, title, textW, 2);
  let ty = portraitY + 78;
  for (const line of titleLines) {
    ctx.fillText(line, textX, ty);
    ty += 72;
  }

  ctx.font = "800 36px system-ui, sans-serif";
  ctx.fillStyle = "#fbbf24";
  const leaderLine = leaderId
    ? `${input.labels.leader}  ${leaderName}  ${displayCardId(leaderId)}`
    : `${input.labels.leader}  ${input.labels.noLeader}`;
  ctx.fillText(fitText(ctx, leaderLine, textW), textX, ty + 12);
  let dotX = textX + ctx.measureText(fitText(ctx, leaderLine, textW)).width + 24;
  const dotR = 15;
  for (const c of leaderColors) {
    ctx.beginPath();
    ctx.arc(dotX + dotR, ty - 2, dotR, 0, Math.PI * 2);
    ctx.fillStyle = colorDotFill(c);
    ctx.fill();
    ctx.strokeStyle = "rgba(248,250,252,0.9)";
    ctx.lineWidth = 3;
    ctx.stroke();
    dotX += dotR * 2 + 14;
  }

  ctx.fillStyle = "#e2e8f0";
  ctx.font = "800 34px system-ui, sans-serif";
  ctx.fillText(`${input.labels.cardsN}  ·  ${input.labels.uniqueN}`, textX, ty + 64);

  const subtitle = String(input.subtitle || "").trim();
  if (subtitle) {
    ctx.fillStyle = "#94a3b8";
    ctx.font = "700 28px system-ui, sans-serif";
    const metaLines = wrapLines(ctx, subtitle, textW, 4);
    let my = ty + 118;
    const metaBottom = portraitY + portraitH - 8;
    for (const line of metaLines) {
      if (my > metaBottom) break;
      ctx.fillText(line, textX, my);
      my += 36;
    }
  }

  ctx.fillStyle = "#fbbf24";
  ctx.fillRect(0, heroH - 6, W, 6);

  const structY = heroH + sectionGap;
  roundRect(ctx, pad, structY, W - pad * 2, structH, 24);
  ctx.fillStyle = "rgba(15, 23, 42, 0.92)";
  ctx.fill();

  const innerX = pad + 28;
  const innerW = W - pad * 2 - 56;
  const splitGap = 24;
  const chartY = structY + 16;
  const chartH = structH - 32;
  const exportCharts = [
    { title: input.labels.costCurve, color: "#38bdf8", keys: costKeys, bucket: costBucket },
    { title: input.labels.powerCurve, color: "#fbbf24", keys: powerKeys, bucket: powerBucket },
    { title: input.labels.counterCurve, color: "#34d399", keys: counterKeys, bucket: counterBucket },
  ].filter((c) => c.keys.length > 0);
  const totalBars = exportCharts.reduce((sum, c) => sum + c.keys.length, 0) || 1;
  const gaps = Math.max(0, exportCharts.length - 1) * splitGap;
  const unit = (innerW - gaps) / totalBars;
  let chartX = innerX;
  for (const chart of exportCharts) {
    const chartW = unit * chart.keys.length;
    drawBarChart(ctx, chartX, chartY, chartW, chartH, chart.title, chart.color, chart.keys, chart.bucket);
    chartX += chartW + splitGap;
  }

  const gridTop = structY + structH + sectionGap;
  const gridBottom = H - footerH;
  const gridAreaH = Math.max(80, gridBottom - gridTop);
  const gridAreaW = W - pad * 2;
  const gap = 16;

  let best = { cols: 6, cardW: 300, cardH: 420 };
  const nCards = Math.max(1, packed.length);
  for (let tryCols = 5; tryCols <= 7; tryCols++) {
    const cw = Math.floor((gridAreaW - gap * (tryCols - 1)) / tryCols);
    const rows = Math.ceil(nCards / tryCols);
    const chCap = Math.floor((gridAreaH - gap * (rows - 1)) / rows);
    const ch = Math.min(Math.round(cw * 1.4), chCap);
    if (cw >= 240 && ch >= 280) {
      best = { cols: tryCols, cardW: cw, cardH: ch };
      break;
    }
    best = { cols: tryCols, cardW: cw, cardH: Math.max(240, ch) };
  }

  const { cols, cardW, cardH } = best;
  packed.forEach((card, idx) => {
    const col = idx % cols;
    const row = Math.floor(idx / cols);
    const x = pad + col * (cardW + gap);
    const y = gridTop + row * (cardH + gap);
    const img = images.get(card.id) || null;
    roundRect(ctx, x, y, cardW, cardH, 18);
    ctx.fillStyle = "rgba(15, 23, 42, 0.9)";
    ctx.fill();
    if (img) {
      ctx.save();
      roundRect(ctx, x, y, cardW, cardH, 18);
      ctx.clip();
      drawFromTop(ctx, img, x, y, cardW, cardH);
      ctx.restore();
    } else {
      ctx.fillStyle = "#94a3b8";
      ctx.font = "800 28px system-ui, sans-serif";
      ctx.fillText(fitText(ctx, displayCardId(card.id), cardW - 20), x + 12, y + cardH / 2);
    }
    const accent = TYPE_ACCENT[card.type] || "#94a3b8";
    ctx.fillStyle = accent;
    ctx.fillRect(x, y + 10, 10, cardH - 20);

    const fadeH = Math.round(cardH * 0.5);
    const fade = ctx.createLinearGradient(0, y + cardH - fadeH, 0, y + cardH);
    fade.addColorStop(0, "rgba(2,6,23,0)");
    fade.addColorStop(0.28, "rgba(2,6,23,0.55)");
    fade.addColorStop(1, "rgba(2,6,23,0.94)");
    ctx.fillStyle = fade;
    ctx.fillRect(x, y + cardH - fadeH, cardW, fadeH);

    const idLabel = displayCardId(card.id);
    ctx.textAlign = "left";
    ctx.fillStyle = "#cbd5e1";
    ctx.font = "700 26px system-ui, sans-serif";
    ctx.fillText(fitText(ctx, card.name, cardW - 24), x + 16, y + cardH - 78);
    ctx.fillStyle = "#f8fafc";
    ctx.font = "800 32px system-ui, sans-serif";
    ctx.fillText(fitText(ctx, idLabel, cardW - 24), x + 16, y + cardH - 42);
    ctx.fillStyle = "#fbbf24";
    ctx.font = "800 34px system-ui, sans-serif";
    ctx.fillText(`${input.labels.qty}${card.n}`, x + 16, y + cardH - 12);
  });

  const footerY = H - footerH;
  const qrPad = 10;
  const qrSize = qrCanvas ? qrDraw : 0;
  const qrBox = qrSize + qrPad * 2;
  const qrX = pad;
  const qrY = footerY + Math.floor((footerH - Math.max(qrBox, 72)) / 2);
  if (qrCanvas) {
    roundRect(ctx, qrX, qrY, qrBox, qrBox, 16);
    ctx.fillStyle = "#ffffff";
    ctx.fill();
    const smoothing = ctx.imageSmoothingEnabled;
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(qrCanvas, qrX + qrPad, qrY + qrPad, qrSize, qrSize);
    ctx.imageSmoothingEnabled = smoothing;
  }
  if (includeQr) {
    ctx.textAlign = "left";
    const creditX = qrCanvas ? qrX + qrBox + 28 : pad;
    ctx.fillStyle = "#94a3b8";
    ctx.font = "800 30px system-ui, sans-serif";
    ctx.fillText(input.labels.createdBy, creditX, qrY + qrBox / 2 - 6);
    ctx.fillStyle = "#f8fafc";
    ctx.font = "800 38px system-ui, sans-serif";
    ctx.fillText(SITE_HOST_LABEL, creditX, qrY + qrBox / 2 + 36);
  }

  for (const bmp of images.values()) {
    try {
      if (bmp && typeof (bmp as ImageBitmap).close === "function") {
        (bmp as ImageBitmap).close();
      }
    } catch {
      /* ignore */
    }
  }

  const out = downsample(canvas, OUT_W, OUT_H);
  let blob = await canvasToBlob(out, "image/png");
  if (!blob) blob = await canvasToBlob(out, "image/jpeg", 0.92);
  if (!blob) {
    const tiny = downsample(canvas, Math.round(OUT_W * 0.7), Math.round(OUT_H * 0.7));
    blob = await canvasToBlob(tiny, "image/jpeg", 0.85);
  }
  if (!blob) throw new Error("export failed");
  return { blob, title, width: OUT_W, height: OUT_H };
}

export async function buildDeckImage(input: ExportInput): Promise<{ blob: Blob; title: string; width: number; height: number }> {
  return renderDeckCanvas(input);
}

export async function downloadDeckImage(
  input: ExportInput,
  existingBlob?: Blob,
  existingTitle?: string,
): Promise<void> {
  const { blob, title } =
    existingBlob && existingTitle
      ? { blob: existingBlob, title: existingTitle }
      : await renderDeckCanvas(input);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  const safeName = title.replace(/[\\/:*?"<>|]+/g, "_").slice(0, 60) || "deck";
  a.href = url;
  a.download = `${safeName}.png`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
