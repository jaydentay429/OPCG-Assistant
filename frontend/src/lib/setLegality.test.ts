import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { battleDateBlocks, battleToday, formatBattleDateBlocks, setCodeOf } from "./setLegality.ts";

const phrase = (key: string, vars?: Record<string, string | number>) => {
  const template =
    key === "play.illegal_unreleased"
      ? "{ids} before {date} {set}"
      : key === "play.illegal_ranked"
        ? "{ids} ranked {date} {set}"
        : key === "play.illegal_ranked_assumed"
          ? "assumed 7-day"
          : key;
  let text = template;
  for (const [name, value] of Object.entries(vars || {})) text = text.replaceAll(`{${name}}`, String(value));
  return text;
};

describe("set legality dates", () => {
  it("reads set codes and Malaysia calendar days", () => {
    assert.equal(setCodeOf("op18-001-p1"), "OP18");
    assert.equal(setCodeOf("EB05-004"), "EB05");
    assert.equal(setCodeOf("P-160"), null);
    const formatted = battleToday(new Date("2026-10-13T16:30:00Z"));
    assert.equal(formatted, "2026-10-14");
  });

  it("blocks EB05 and OP18 before release, then opens casual before ranked", () => {
    assert.deepEqual(
      battleDateBlocks("OP17-001", { "EB05-001": 4 }, "casual", "2026-10-13").map((block) => block.reason),
      ["unreleased"],
    );
    assert.equal(battleDateBlocks("EB05-001", { "OP01-016": 4 }, "casual", "2026-10-30").length, 0);
    const rankedEarly = battleDateBlocks("EB05-001", {}, "ranked", "2026-10-30");
    assert.equal(rankedEarly[0]?.reason, "not_ranked_legal");
    assert.equal(rankedEarly[0]?.tournamentLegalDate, "2026-11-06");
    assert.equal(battleDateBlocks("EB05-001", {}, "ranked", "2026-11-06").length, 0);
  });

  it("marks the OP18 tournament date as assumed and keeps older sets open", () => {
    const blocks = battleDateBlocks("OP18-001", { "OP18-011": 1 }, "ranked", "2026-11-20");
    assert.equal(blocks.length, 2);
    assert.equal(blocks.every((block) => block.tournamentLegalAssumed), true);
    assert.equal(blocks[0]?.tournamentLegalDate, "2026-11-27");
    assert.match(formatBattleDateBlocks(blocks, phrase) || "", /assumed 7-day/);
    assert.equal(battleDateBlocks("OP18-060", {}, "casual", "2026-11-20").length, 0);
    assert.equal(battleDateBlocks("OP18-060", {}, "ranked", "2026-11-27").length, 0);
    assert.equal(battleDateBlocks("ST01-001", { "OP01-016": 4 }, "ranked", "2026-10-13").length, 0);
  });
});
