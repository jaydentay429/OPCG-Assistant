import setIndex from "@/generated/set-index.json";

export type SetCardRow = {
  id: string;
  name: string;
};

export type SetIndexEntry = {
  code: string;
  count: number;
  cards: SetCardRow[];
};

const SETS = (Array.isArray(setIndex) ? setIndex : []) as SetIndexEntry[];

export function allSets(): SetIndexEntry[] {
  return SETS;
}

export function getSet(code: string): SetIndexEntry | null {
  const needle = String(code || "").trim().toUpperCase();
  if (!needle) return null;
  return SETS.find((s) => s.code === needle) || null;
}

export function setLabel(code: string): string {
  const c = String(code || "").toUpperCase();
  if (c === "P") return "P 宣傳卡";
  if (c === "DON") return "DON!!";
  const n = c.match(/^(OP|EB|ST|PRB)(\d+)$/);
  if (n) return `${n[1]}-${n[2]}`;
  return c;
}

export function setPageTitle(code: string): string {
  const label = setLabel(code);
  if (code.toUpperCase() === "P") return "P 宣傳卡卡表｜ONE PIECE CARD GAME Promo";
  if (code.toUpperCase() === "DON") return "DON!! 卡表｜ONE PIECE CARD GAME";
  if (/^OP\d+$/i.test(code)) return `${label} 卡表｜OPCG ${code} 補充包全卡列表`;
  if (/^EB\d+$/i.test(code)) return `${label} 卡表｜OPCG Extra Booster 全卡列表`;
  if (/^ST\d+$/i.test(code)) return `${label} 卡表｜OPCG 起始牌組全卡列表`;
  return `${label} 卡表｜OPCG 卡牌列表`;
}

export function setPageDescription(code: string, count: number): string {
  const label = setLabel(code);
  return `查看《ONE PIECE 卡牌對戰》${label}（${code}）全部 ${count} 張卡：卡號、卡名、效果與價格。可從 OPCG 卡牌助手搜尋、組牌或練牌。`;
}
