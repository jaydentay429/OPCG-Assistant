import { API_BASE, cardImagePacksUrl, cardImageUrl } from "@/lib/api";
import { displayCardId } from "@/lib/cardId";

async function fetchImageBitmap(url: string, cache: RequestCache = "force-cache"): Promise<ImageBitmap | null> {
  try {
    const res = await fetch(url, { mode: "cors", credentials: "omit", cache });
    if (!res.ok) return null;
    const blob = await res.blob();
    if (!blob || blob.size < 32) return null;
    return await createImageBitmap(blob);
  } catch {
    return null;
  }
}

async function loadCardBitmap(cardId: string): Promise<ImageBitmap | null> {
  const candidates = [
    cardImagePacksUrl(cardId),
    cardImageUrl(cardId),
    `${cardImageUrl(cardId)}&retry=1`,
  ];
  const seen = new Set<string>();
  for (const url of candidates) {
    if (!url || seen.has(url)) continue;
    seen.add(url);
    const cached = await fetchImageBitmap(url, "force-cache");
    if (cached) return cached;
    const fresh = await fetchImageBitmap(url, "reload");
    if (fresh) return fresh;
  }
  return null;
}

async function mapPool<T, R>(items: T[], concurrency: number, fn: (item: T) => Promise<R>): Promise<R[]> {
  const out: R[] = new Array(items.length);
  let i = 0;
  async function worker() {
    while (i < items.length) {
      const idx = i++;
      out[idx] = await fn(items[idx]!);
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, Math.max(1, items.length)) }, () => worker()));
  return out;
}

export type BinderPageExportInput = {
  page: number;
  title: string;
  ownerName?: string;
  slots: (string | null)[];
  siteLabel?: string;
};

/** Match UI binder-sheet: 684×921 bg with 3×3 pockets; cards ~83% of cell. */
const SHEET_W = 684;
const SHEET_H = 921;
const CARD_SCALE = 0.83;

/** Render one binder page (left+right sheets) using the real binder pocket background. */
export async function exportBinderPageImage(input: BinderPageExportInput): Promise<string> {
  const slots = Array.from({ length: 18 }, (_, i) => input.slots[i] || null);
  const [sheetBg, bitmaps] = await Promise.all([
    fetchImageBitmap(`${window.location.origin}/binder-sheet-bg.png`),
    // Lower concurrency to avoid burst failures against image/proxy endpoints.
    mapPool(slots, 3, async (cid) => (cid ? loadCardBitmap(cid) : null)),
  ]);

  const pad = 36;
  const sheetGap = 28;
  const headerH = 52;
  const footerH = 48;
  const width = pad * 2 + SHEET_W * 2 + sheetGap;
  const height = pad + headerH + SHEET_H + pad + footerH;

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas unavailable");

  const bg = ctx.createLinearGradient(0, 0, width, height);
  bg.addColorStop(0, "#0b1220");
  bg.addColorStop(1, "#1e293b");
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, width, height);

  // One header line only (no "Page x/10" title). Prefer custom page title, else @user · Binder n/10.
  const pageTitle = (input.title || "").trim();
  const subParts = [
    input.ownerName ? `@${input.ownerName}` : "",
    pageTitle || `Binder ${input.page}/10`,
  ].filter(Boolean);
  ctx.fillStyle = "#e2e8f0";
  ctx.font = "600 26px system-ui, -apple-system, sans-serif";
  ctx.fillText(subParts.join(" · "), pad, pad + 34);

  function drawSheet(startSlot: number, originX: number, originY: number) {
    if (sheetBg) {
      ctx.drawImage(sheetBg, originX, originY, SHEET_W, SHEET_H);
    } else {
      ctx.fillStyle = "#1a2332";
      roundRectPath(ctx, originX, originY, SHEET_W, SHEET_H, 12);
      ctx.fill();
      ctx.strokeStyle = "rgba(148, 163, 184, 0.25)";
      ctx.lineWidth = 2;
      for (let i = 1; i < 3; i++) {
        const gx = originX + (SHEET_W * i) / 3;
        const gy = originY + (SHEET_H * i) / 3;
        ctx.beginPath();
        ctx.moveTo(gx, originY);
        ctx.lineTo(gx, originY + SHEET_H);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(originX, gy);
        ctx.lineTo(originX + SHEET_W, gy);
        ctx.stroke();
      }
    }

    const cellW = SHEET_W / 3;
    const cellH = SHEET_H / 3;
    const cardW = cellW * CARD_SCALE;
    const cardH = cellH * CARD_SCALE;

    for (let i = 0; i < 9; i++) {
      const slotIdx = startSlot + i;
      const col = i % 3;
      const row = Math.floor(i / 3);
      const cellX = originX + col * cellW;
      const cellY = originY + row * cellH;
      const x = cellX + (cellW - cardW) / 2;
      const y = cellY + (cellH - cardH) / 2;
      const bmp = bitmaps[slotIdx];
      const cid = slots[slotIdx];

      if (bmp) {
        ctx.save();
        roundRectPath(ctx, x, y, cardW, cardH, 6);
        ctx.clip();
        ctx.drawImage(bmp, x, y, cardW, cardH);
        ctx.restore();
      } else if (cid) {
        // Soft placeholder only — keep layout; avoid looking like a permanent “card number” tile.
        ctx.fillStyle = "rgba(15, 23, 42, 0.45)";
        roundRectPath(ctx, x, y, cardW, cardH, 6);
        ctx.fill();
        ctx.strokeStyle = "rgba(148, 163, 184, 0.35)";
        ctx.lineWidth = 1;
        roundRectPath(ctx, x + 0.5, y + 0.5, cardW - 1, cardH - 1, 6);
        ctx.stroke();
        ctx.fillStyle = "#94a3b8";
        ctx.font = "500 11px system-ui, sans-serif";
        ctx.textAlign = "center";
        ctx.fillText(displayCardId(cid), x + cardW / 2, y + cardH / 2);
        ctx.textAlign = "start";
      }
    }

    ctx.strokeStyle = "rgba(15, 23, 42, 0.45)";
    ctx.lineWidth = 3;
    roundRectPath(ctx, originX + 1.5, originY + 1.5, SHEET_W - 3, SHEET_H - 3, 10);
    ctx.stroke();
  }

  const originY = pad + headerH;
  drawSheet(0, pad, originY);
  drawSheet(9, pad + SHEET_W + sheetGap, originY);

  ctx.fillStyle = "#94a3b8";
  ctx.font = "600 22px system-ui, -apple-system, sans-serif";
  ctx.fillText(input.siteLabel || "optcgassistant.com", pad, height - 18);

  return canvas.toDataURL("image/png");
}

function roundRectPath(
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

export function downloadDataUrl(dataUrl: string, filename: string) {
  const a = document.createElement("a");
  a.href = dataUrl;
  a.download = filename;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
}
