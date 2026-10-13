import setLegalityDocument from "../../../index/set_legality.json" with { type: "json" };

export type BattleLegalityMode = "casual" | "ranked";
export type BattleDateReason = "unreleased" | "not_ranked_legal";

type SetRow = {
  code: string;
  release_date: string;
  tournament_legal_date: string;
  tournament_legal_assumed?: boolean;
};

type SetLegalityDocument = {
  timezone: string;
  sets: SetRow[];
};

const documentData = setLegalityDocument as SetLegalityDocument;

const SETS = new Map(documentData.sets.map((row) => [row.code.toUpperCase(), row]));

const SET_CODE = /^([A-Z]+\d+)-/i;

export function setCodeOf(cardId: string): string | null {
  const match = SET_CODE.exec(String(cardId || "").trim().toUpperCase());
  return match ? match[1].toUpperCase() : null;
}

/** Calendar day in the schedule timezone. `en-CA` formats as YYYY-MM-DD. */
export function battleToday(now = new Date(), timeZone = documentData.timezone): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const year = parts.find((part) => part.type === "year")?.value ?? "1970";
  const month = parts.find((part) => part.type === "month")?.value ?? "01";
  const day = parts.find((part) => part.type === "day")?.value ?? "01";
  return `${year}-${month}-${day}`;
}

export type BattleDateBlock = {
  cardId: string;
  setCode: string;
  reason: BattleDateReason;
  releaseDate: string;
  tournamentLegalDate: string;
  tournamentLegalAssumed: boolean;
};

function deckIds(leaderId: string, cards: Record<string, number> | null | undefined): string[] {
  const ids: string[] = [];
  const leader = String(leaderId || "").trim();
  if (leader) ids.push(leader);
  for (const [cardId, qty] of Object.entries(cards || {})) {
    if (Number(qty || 0) <= 0) continue;
    const text = String(cardId || "").trim();
    if (text) ids.push(text);
  }
  return ids;
}

/** Date gate only. Missing effect data is enforced by the API, which has the effect library. */
export function battleDateBlocks(
  leaderId: string,
  cards: Record<string, number> | null | undefined,
  mode: BattleLegalityMode,
  onDate = battleToday(),
): BattleDateBlock[] {
  const seen = new Set<string>();
  const blocks: BattleDateBlock[] = [];
  for (const cardId of deckIds(leaderId, cards)) {
    const key = cardId.toUpperCase();
    if (seen.has(key)) continue;
    seen.add(key);
    const setCode = setCodeOf(cardId);
    const spec = setCode ? SETS.get(setCode) : undefined;
    if (!spec) continue;
    let reason: BattleDateReason | null = null;
    if (onDate < spec.release_date) reason = "unreleased";
    else if (mode === "ranked" && onDate < spec.tournament_legal_date) reason = "not_ranked_legal";
    if (!reason) continue;
    blocks.push({
      cardId,
      setCode: spec.code,
      reason,
      releaseDate: spec.release_date,
      tournamentLegalDate: spec.tournament_legal_date,
      tournamentLegalAssumed: Boolean(spec.tournament_legal_assumed),
    });
  }
  return blocks;
}

type Phrase = (key: string, vars?: Record<string, string | number>) => string;

export function formatBattleDateBlocks(blocks: BattleDateBlock[], phrase: Phrase): string | null {
  if (!blocks.length) return null;
  const parts: string[] = [];
  const unreleased = blocks.filter((block) => block.reason === "unreleased");
  const ranked = blocks.filter((block) => block.reason === "not_ranked_legal");
  if (unreleased.length) {
    const first = unreleased[0];
    parts.push(
      phrase("play.illegal_unreleased", {
        ids: unreleased.map((block) => block.cardId).join(", "),
        set: first.setCode,
        date: first.releaseDate,
      }),
    );
  }
  if (ranked.length) {
    const first = ranked[0];
    parts.push(
      phrase("play.illegal_ranked", {
        ids: ranked.map((block) => block.cardId).join(", "),
        set: first.setCode,
        date: first.tournamentLegalDate,
      }),
    );
    if (ranked.some((block) => block.tournamentLegalAssumed)) {
      parts.push(phrase("play.illegal_ranked_assumed"));
    }
  }
  return parts.join(" ");
}
