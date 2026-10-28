import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { searchResultsScrollBehavior, searchResultsScrollTop } from "./searchScroll.ts";

describe("search page scroll", () => {
  it("uses an instant jump when reduced motion is requested", () => {
    assert.equal(searchResultsScrollBehavior(true), "auto");
    assert.equal(searchResultsScrollBehavior(false), "smooth");
  });

  it("aligns the results block under the sticky bar and clamps to the page top", () => {
    assert.equal(searchResultsScrollTop(820, 2690, 48), 3462);
    assert.equal(searchResultsScrollTop(48, 0, 48), 0);
    assert.equal(searchResultsScrollTop(-20, 0, 48), 0);
    assert.equal(searchResultsScrollTop(Number.NaN, 10, 48), 0);
  });
});
