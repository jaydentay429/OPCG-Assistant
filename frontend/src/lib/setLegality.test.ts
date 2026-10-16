import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { battleDateBlocks, battleDateFromServer, battleToday, formatBattleDateBlocks, setCodeOf } from "./setLegality.ts";

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

  it("does not block EB05 or OP18 before release in casual or ranked", () => {
    assert.deepEqual(battleDateBlocks("OP17-001", { "EB05-001": 4 }, "casual", "2026-10-13"), []);
    assert.deepEqual(battleDateBlocks("EB05-001", {}, "ranked", "2026-10-30"), []);
    assert.deepEqual(battleDateBlocks("OP18-001", { "OP18-011": 1 }, "ranked", "2026-11-20"), []);
    assert.deepEqual(battleDateBlocks("OP18-060", {}, "casual", "2026-10-13"), []);
    assert.equal(formatBattleDateBlocks([], phrase), null);
  });

  it("accepts a server YYYY-MM-DD and rejects anything else", () => {
    assert.equal(battleDateFromServer("2026-11-27"), "2026-11-27");
    assert.equal(battleDateFromServer(" 2026-11-27 "), "2026-11-27");
    assert.equal(battleDateFromServer(""), null);
    assert.equal(battleDateFromServer(null), null);
    assert.equal(battleDateFromServer("2026-02-31"), null);
    assert.equal(battleDateFromServer("11/27/2026"), null);
  });
});
