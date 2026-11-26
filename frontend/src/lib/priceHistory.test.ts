import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { chartHistory, daysSince } from "./priceHistory";

describe("chartHistory", () => {
  it("extends an unchanged price to the last-seen date", () => {
    const out = chartHistory([{ ts: "2026-07-31T09:47:08+00:00", price: 120 }], 120, "2026-09-14T04:30:02+00:00");
    assert.equal(out.length, 2);
    assert.deepEqual(out[1], { ts: "2026-09-14T04:30:02+00:00", price: 120 });
  });

  it("leaves history alone when last seen is the same day or the price differs", () => {
    const one = [{ ts: "2026-11-21T04:00:08+00:00", price: 50 }];
    assert.equal(chartHistory(one, 50, "2026-11-21T10:00:00+00:00").length, 1);
    assert.equal(chartHistory(one, 60, "2026-11-25T10:00:00+00:00").length, 1);
    assert.equal(chartHistory(one, null, "2026-11-25T10:00:00+00:00").length, 1);
    assert.deepEqual(chartHistory([], 50, "2026-11-25T10:00:00+00:00"), []);
  });
});

describe("daysSince", () => {
  it("counts whole days", () => {
    const now = Date.parse("2026-11-26T12:00:00Z");
    assert.equal(daysSince("2026-09-14T04:30:02+00:00", now), 73);
    assert.equal(daysSince("", now), null);
  });
});
