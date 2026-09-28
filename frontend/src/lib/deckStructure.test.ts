import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { summarizeDeckStructure } from "./deckStructure";

const leader = { card_type: "Leader", cost: 5, power: 5000, counter: 0, name: "魯夫" };
const character = { card_type: "Character", cost: 2, power: 4000, counter: 1000, name: "娜美" };

function leaderCount(
  leaderId: string | null,
  cards: Record<string, number>,
  stats: Record<string, typeof leader>,
) {
  const summary = summarizeDeckStructure(leaderId, cards, stats, "zh-Hant");
  return summary.types.find((row) => row.key === "Leader")?.n ?? 0;
}

describe("summarizeDeckStructure type mix", () => {
  it("counts the leader slot as one and leaves it off the cost curve", () => {
    const summary = summarizeDeckStructure(
      "OP01-001",
      { "OP01-002": 4 },
      { "OP01-001": leader, "OP01-002": character },
      "zh-Hant",
    );
    assert.equal(leaderCount("OP01-001", { "OP01-002": 4 }, { "OP01-001": leader, "OP01-002": character }), 1);
    assert.equal(summary.types.find((row) => row.key === "Character")?.n, 4);
    assert.deepEqual(summary.costCurve, [{ key: "2", n: 4 }]);
    assert.deepEqual(summary.powerCurve, [{ key: "4k", n: 4 }]);
  });

  it("does not add main-deck leader copies on top of the slot", () => {
    const cards = { "OP01-001": 8, "OP01-002": 4 };
    const stats = { "OP01-001": leader, "OP01-002": character };
    assert.equal(leaderCount("OP01-001", cards, stats), 1);
    const summary = summarizeDeckStructure("OP01-001", cards, stats, "zh-Hant");
    assert.equal(summary.types.find((row) => row.key === "Character")?.n, 4);
  });

  it("counts one leader when the card only exists in the main deck", () => {
    const stats = { "ST01-001": { ...leader, card_type: "領袖" } };
    assert.equal(leaderCount(null, { "ST01-001": 9 }, stats), 1);
    const summary = summarizeDeckStructure(null, { "ST01-001": 9 }, stats, "en");
    assert.deepEqual(summary.types, [{ key: "Leader", n: 1 }]);
    assert.equal(summary.powerCurve.length, 0);
    assert.equal(summary.counterCurve.length, 0);
  });

  it("still counts one when several leader rows are stored in the main deck", () => {
    const stats = {
      "OP01-001": leader,
      "ST01-001": leader,
    };
    assert.equal(
      leaderCount(null, { "OP01-001": 4, "ST01-001": 5 }, stats),
      1,
    );
  });
});
