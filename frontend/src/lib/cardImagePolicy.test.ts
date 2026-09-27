import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { isSuppressedCardImage } from "./cardImagePolicy";

describe("isSuppressedCardImage", () => {
  it("hides the mislabeled EB05-046 packs file and leaves other ids alone", () => {
    assert.equal(isSuppressedCardImage("EB05-046"), true);
    assert.equal(isSuppressedCardImage("eb05-046"), true);
    assert.equal(isSuppressedCardImage("EB05-048"), false);
    assert.equal(isSuppressedCardImage("EB05-010"), false);
    assert.equal(isSuppressedCardImage("OP18-112"), false);
  });
});
