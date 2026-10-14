import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { localizeBattleApiError } from "./battleErrors.ts";

describe("battle API errors", () => {
  it("localizes the leaders-in-main deck error", () => {
    const t = (key: string) => (key === "play.deck_no_leaders_in_main" ? "主牌組不能放入領袖卡。" : key);
    assert.equal(localizeBattleApiError("Main deck cannot include Leaders.", t), "主牌組不能放入領袖卡。");
    assert.equal(localizeBattleApiError("Room not found.", t), "Room not found.");
  });
});
