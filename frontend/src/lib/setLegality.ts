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

const SET_CODE = /^([A-Z]+\d+)-/i;

export function setCodeOf(cardId: string): string | null {
  const match = SET_CODE.exec(String(cardId || "").trim().toUpperCase());
  return match ? match[1].toUpperCase() : null;
}

const ISO_DAY = /^(\d{4})-(\d{2})-(\d{2})$/;

/** Server battle day from `/battle/ai-decks`. Empty or invalid means the API decides. */
export function battleDateFromServer(value: string | null | undefined): string | null {
  const day = String(value || "").trim();
  if (!ISO_DAY.test(day)) return null;
  const parsed = new Date(`${day}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return null;
  const [year, month, date] = day.split("-").map((part) => Number(part));
  if (
    parsed.getUTCFullYear() !== year ||
    parsed.getUTCMonth() + 1 !== month ||
    parsed.getUTCDate() !== date
  ) {
    return null;
  }
  return day;
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

/** Release and tournament dates do not block import. Effect data is enforced by the API. */
export function battleDateBlocks(
  _leaderId: string,
  _cards: Record<string, number> | null | undefined,
  _mode: BattleLegalityMode,
  _onDate?: string,
): BattleDateBlock[] {
  void _onDate;
  return [];
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
