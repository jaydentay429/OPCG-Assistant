import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { localizeBattleApiError } from "./battleErrors.ts";

describe("battle API errors", () => {
  it("localizes the leaders-in-main deck error", () => {
    const t = (key: string) => (key === "play.deck_no_leaders_in_main" ? "主牌組不能放入領袖卡。" : key);
    assert.equal(localizeBattleApiError("Main deck cannot include Leaders.", t), "主牌組不能放入領袖卡。");
    assert.equal(localizeBattleApiError("Room not found.", t), "Room not found.");
  });

  it("localizes banned-card import errors, including more than one sentence", () => {
    const t = (key: string, vars?: Record<string, string | number>) => {
      if (key !== "play.banned_card") return key;
      return `禁用卡 ${vars?.ids} 不能放入卡組（${vars?.date} 起禁用）。`;
    };
    assert.equal(
      localizeBattleApiError(
        "Banned card OP14-020 cannot be included in a deck (banned from 2026-10-12).",
        t,
      ),
      "禁用卡 OP14-020 不能放入卡組（2026-10-12 起禁用）。",
    );
    assert.equal(
      localizeBattleApiError(
        "Banned card OP14-020, OP14-020-P1 cannot be included in a deck (banned from 2026-10-12). Banned card OP01-001 cannot be included in a deck (banned from 2026-01-01).",
        t,
      ),
      "禁用卡 OP14-020, OP14-020-P1 不能放入卡組（2026-10-12 起禁用）。 禁用卡 OP01-001 不能放入卡組（2026-01-01 起禁用）。",
    );
  });

  it("localizes banned-pair errors from battle (English) and deck save (simplified)", () => {
    const copy: Record<string, string> = {
      "zh-Hant": "禁用組合 {a} 與 {b} 不能放在同一套卡組（{date} 起）。",
      "zh-Hans": "禁用组合 {a} 与 {b} 不能放在同一套卡组（{date} 起）。",
      en: "Banned pair {a} and {b} cannot be in the same deck (from {date}).",
    };
    const tFor = (lang: keyof typeof copy) => (key: string, vars?: Record<string, string | number>) => {
      if (key !== "play.banned_pair") return key;
      return copy[lang].replaceAll("{a}", String(vars?.a)).replaceAll("{b}", String(vars?.b)).replaceAll("{date}", String(vars?.date));
    };
    const english = "Banned pair OP11-040-P1 and OP11-067-P1 cannot be in the same deck (from 2026-04-10).";
    const hans = "禁用组合 OP11-040 与 OP08-069 不能放在同一套卡组（2026-04-10 起）。";
    assert.equal(
      localizeBattleApiError(english, tFor("zh-Hant")),
      "禁用組合 OP11-040-P1 與 OP11-067-P1 不能放在同一套卡組（2026-04-10 起）。",
    );
    assert.equal(
      localizeBattleApiError(english, tFor("zh-Hans")),
      "禁用组合 OP11-040-P1 与 OP11-067-P1 不能放在同一套卡组（2026-04-10 起）。",
    );
    assert.equal(localizeBattleApiError(english, tFor("en")), english);
    assert.equal(
      localizeBattleApiError(hans, tFor("zh-Hant")),
      "禁用組合 OP11-040 與 OP08-069 不能放在同一套卡組（2026-04-10 起）。",
    );
    assert.equal(
      localizeBattleApiError(hans, tFor("en")),
      "Banned pair OP11-040 and OP08-069 cannot be in the same deck (from 2026-04-10).",
    );
    assert.equal(
      localizeBattleApiError(
        "Banned pair OP11-040, OP11-040-P1 and OP11-067, OP11-067-P1 cannot be in the same deck (from 2026-04-10). Banned pair OP07-115 and EB04-058 cannot be in the same deck (from 2026-05-01).",
        tFor("zh-Hant"),
      ),
      "禁用組合 OP11-040, OP11-040-P1 與 OP11-067, OP11-067-P1 不能放在同一套卡組（2026-04-10 起）。 禁用組合 OP07-115 與 EB04-058 不能放在同一套卡組（2026-05-01 起）。",
    );
    assert.equal(localizeBattleApiError("Room not found.", tFor("zh-Hant")), "Room not found.");
  });

  it("localizes a missing battle-effect error on Chinese pages", () => {
    const copy: Record<string, string> = {
      "zh-Hant": "{ids} 還沒有對戰效果數據，暫時不能用於對戰。",
      "zh-Hans": "{ids} 还没有对战效果数据，暂时不能用于对战。",
      en: "{ids} cannot be used in battle because battle effect data is missing.",
    };
    const tFor = (lang: keyof typeof copy) => (key: string, vars?: Record<string, string | number>) => {
      if (key === "play.banned_pair") {
        return `禁用組合 ${vars?.a} 與 ${vars?.b} 不能放在同一套卡組（${vars?.date} 起）。`;
      }
      if (key !== "play.illegal_no_effect") return key;
      return copy[lang].replaceAll("{ids}", String(vars?.ids));
    };
    const english = "OP18-003 cannot be used in battle because battle effect data is missing.";
    assert.equal(localizeBattleApiError(english, tFor("zh-Hant")), "OP18-003 還沒有對戰效果數據，暫時不能用於對戰。");
    assert.equal(localizeBattleApiError(english, tFor("zh-Hans")), "OP18-003 还没有对战效果数据，暂时不能用于对战。");
    assert.equal(localizeBattleApiError(english, tFor("en")), english);
    assert.equal(
      localizeBattleApiError(
        "Banned pair OP11-040 and OP11-067 cannot be in the same deck (from 2025-08-30). OP18-003 cannot be used in battle because battle effect data is missing.",
        tFor("zh-Hant"),
      ),
      "禁用組合 OP11-040 與 OP11-067 不能放在同一套卡組（2025-08-30 起）。 OP18-003 還沒有對戰效果數據，暫時不能用於對戰。",
    );
  });
});
