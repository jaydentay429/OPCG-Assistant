import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { formatLeaderDate, leaderDisplayName, leaderIsIndexable, topdeckDateIso } from "./leaders";

describe("leaders helpers", () => {
  it("picks the name for each language", () => {
    const row = { leader: "OP01-001", name: "羅羅亞·索隆", name_hans: "罗罗诺亚·索隆", name_en: "Roronoa Zoro" };
    assert.equal(leaderDisplayName(row, "zh-Hant"), "羅羅亞·索隆");
    assert.equal(leaderDisplayName(row, "zh-Hans"), "罗罗诺亚·索隆");
    assert.equal(leaderDisplayName(row, "en"), "Roronoa Zoro");
    assert.equal(leaderDisplayName({ leader: "OP99-001" }, "en"), "OP99-001");
  });

  it("indexes only leaders with enough decks", () => {
    assert.equal(leaderIsIndexable({ decks: 5 }), true);
    assert.equal(leaderIsIndexable({ decks: 4 }), false);
    assert.equal(leaderIsIndexable(null), false);
  });

  it("formats dates", () => {
    assert.equal(topdeckDateIso("11/2/2026"), "2026-11-02");
    assert.equal(topdeckDateIso("bad"), "");
    assert.equal(formatLeaderDate("2026-11-02", "zh-Hant"), "02/11/2026");
    assert.equal(formatLeaderDate("2026-11-02", "zh-Hans"), "2026/11/02");
    assert.equal(formatLeaderDate("2026-11-02", "en"), "11/02/2026");
  });
});
