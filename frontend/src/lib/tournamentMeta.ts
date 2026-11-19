import type { Lang } from "@/lib/i18n";
import { fetchTopdecksMeta } from "@/lib/api";

const SET_KIND_RANK: Record<string, number> = { OP: 4, EB: 3, ST: 2, PRB: 1 };
const SET_IN_KEY_RE = /(OP|EB|ST|PRB)(\d+)/gi;
const LEADING_SET_RE = /^(op|eb|st|prb)-?(\d+)/i;

export type TournamentMetaLike = {
  slug?: string;
  title?: string;
  modified?: string;
  deck_count?: number;
};

/** Group JP/EN meta pages into short set labels like OP17 or EB05+OP18. */
export function metaCategoryKey(slug: string): string {
  const body = String(slug || "")
    .toLowerCase()
    .replace(/^(japan|japanese|english-format|english|en-format|jp-format)-/, "");
  const parts: string[] = [];
  let rest = body;
  while (true) {
    const m = rest.match(LEADING_SET_RE);
    if (!m) break;
    parts.push(`${m[1].toUpperCase()}${String(parseInt(m[2], 10)).padStart(2, "0")}`);
    rest = rest.slice(m[0].length).replace(/^-/, "");
    if (!LEADING_SET_RE.test(rest)) break;
  }
  return parts.length ? parts.join("+") : slug;
}

export function setCodesInMetaKey(key: string): Array<{ kind: string; n: number }> {
  const out: Array<{ kind: string; n: number }> = [];
  const re = new RegExp(SET_IN_KEY_RE.source, SET_IN_KEY_RE.flags);
  let m: RegExpExecArray | null;
  while ((m = re.exec(String(key || "")))) {
    out.push({ kind: m[1].toUpperCase(), n: parseInt(m[2], 10) });
  }
  return out;
}

/** Rank a label by its newest set code, so EB05+OP18 ranks with OP18, not EB05. */
export function metaCategoryRank(key: string): [number, number, string] {
  const codes = setCodesInMetaKey(key);
  if (!codes.length) return [0, 0, key];
  const n = Math.max(...codes.map((c) => c.n));
  const kind = Math.max(...codes.filter((c) => c.n === n).map((c) => SET_KIND_RANK[c.kind] || 0));
  return [n, kind, key];
}

export function compareMetaCategoryKeys(a: string, b: string): number {
  const ra = metaCategoryRank(a);
  const rb = metaCategoryRank(b);
  if (ra[0] !== rb[0]) return rb[0] - ra[0];
  if (ra[1] !== rb[1]) return rb[1] - ra[1];
  return String(ra[2]).localeCompare(String(rb[2]));
}

export function formatMetaLabel(keys: string[]): string {
  return keys.filter(Boolean).join(" / ");
}

function modifiedTime(row: TournamentMetaLike): number {
  const raw = String(row.modified || "").trim();
  if (!raw) return 0;
  const t = Date.parse(raw);
  return Number.isFinite(t) ? t : 0;
}

/**
 * Latest tournament environments from JP/EN meta data.
 *
 * "Latest" means the newest `modified` timestamp among unique category keys
 * (JP and EN pages for the same environment are merged). If dates are missing,
 * fall back to the highest set number in the key (EB05+OP18 → 18).
 *
 * Returns up to `limit` keys, newest first, e.g. ["EB05+OP18", "OP17"].
 */
export function latestTournamentMetaKeys(
  formats:
    | {
        jp?: { metas?: TournamentMetaLike[] };
        en?: { metas?: TournamentMetaLike[] };
      }
    | undefined,
  limit = 2,
): string[] {
  const rows: TournamentMetaLike[] = [
    ...((formats?.jp?.metas || []) as TournamentMetaLike[]),
    ...((formats?.en?.metas || []) as TournamentMetaLike[]),
  ];
  const best = new Map<string, { modified: number; rank: ReturnType<typeof metaCategoryRank> }>();
  for (const row of rows) {
    const slug = String(row?.slug || "").trim();
    if (!slug) continue;
    const key = metaCategoryKey(slug);
    if (!key) continue;
    const modified = modifiedTime(row);
    const prev = best.get(key);
    if (!prev || modified > prev.modified) {
      best.set(key, { modified, rank: metaCategoryRank(key) });
    }
  }
  return [...best.entries()]
    .sort((a, b) => {
      if (a[1].modified !== b[1].modified) return b[1].modified - a[1].modified;
      return compareMetaCategoryKeys(a[0], b[0]);
    })
    .slice(0, Math.max(0, limit))
    .map(([key]) => key);
}

export function tournamentSetsFallback(lang: Lang): string {
  if (lang === "en") return "the latest meta";
  if (lang === "zh-Hans") return "最新环境";
  return "最新環境";
}

export function tournamentDocumentTitle(lang: Lang, keys: string[]): string {
  const sets = formatMetaLabel(keys);
  if (lang === "en") {
    return sets
      ? `${sets} Tournament Deck Lists | OPCG Assistant`
      : "Tournament Deck Lists | OPCG Assistant";
  }
  if (lang === "zh-Hans") {
    return sets
      ? `${sets} Deck List 赛事卡组 | OPCG Assistant 比赛卡组浏览`
      : "Deck List 赛事卡组 | OPCG Assistant 比赛卡组浏览";
  }
  return sets
    ? `${sets} Deck List 賽事卡組 | OPCG Assistant 比賽卡組瀏覽`
    : "Deck List 賽事卡組 | OPCG Assistant 比賽卡組瀏覽";
}

export function tournamentPageDescription(lang: Lang, keys: string[]): string {
  const sets = formatMetaLabel(keys) || tournamentSetsFallback(lang);
  if (lang === "en") {
    return `Browse ONE PIECE CARD GAME tournament deck lists on optcgassistant.com: filter ${sets} and other metas, study winning decks, and import a list into the OPCG Assistant builder or practice battle.`;
  }
  if (lang === "zh-Hans") {
    return `在 optcgassistant.com 浏览 ONE PIECE CARD GAME 公开赛事卡组：查看 ${sets} 等环境 deck list，研究 meta，并可一键导入到 OPCG Assistant 卡组构筑与对战练习。`;
  }
  return `在 optcgassistant.com 瀏覽 ONE PIECE CARD GAME 公開賽事卡組：查看 ${sets} 等環境 deck list，研究 meta，並可一鍵導入到 OPCG Assistant 卡組構築與對戰練習。`;
}

export function tournamentSeoIntro(keys: string[]): string {
  const sets = formatMetaLabel(keys) || "最新環境";
  return `在 optcgassistant.com 瀏覽 ONE PIECE CARD GAME 公開賽事卡組：依環境（如 ${sets}）、領袖與比賽篩選，並可導入卡組構築與對戰練習。列表會隨資料更新。`;
}

export function tournamentMetaKeywords(keys: string[]): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  const add = (s: string) => {
    const v = s.trim();
    if (!v || seen.has(v)) return;
    seen.add(v);
    out.push(v);
  };
  for (const key of keys) {
    add(`${key} deck list`);
    add(`${key} decklist`);
    for (const code of setCodesInMetaKey(key)) {
      const compact = `${code.kind}${String(code.n).padStart(2, "0")}`;
      const hyphen = `${code.kind}-${String(code.n).padStart(2, "0")}`;
      add(`${compact} deck list`);
      add(`${hyphen} decklist`);
    }
  }
  add("ONE PIECE TCG tournament decks");
  add("OPCG meta");
  add("賽事卡組");
  add("比赛卡组");
  return out;
}

export async function loadLatestTournamentMetaKeys(limit = 2): Promise<string[]> {
  try {
    const res = await fetchTopdecksMeta();
    return latestTournamentMetaKeys(res.formats, limit);
  } catch {
    return [];
  }
}
