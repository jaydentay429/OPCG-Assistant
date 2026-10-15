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
});
