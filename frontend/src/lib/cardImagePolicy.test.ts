import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { isSuppressedCardImage } from "./cardImagePolicy";

describe("isSuppressedCardImage", () => {
  it("lets EB05-046 and EB05-048 request their own filenames", () => {
    assert.equal(isSuppressedCardImage("EB05-046"), false);
    assert.equal(isSuppressedCardImage("eb05-046"), false);
    assert.equal(isSuppressedCardImage("EB05-048"), false);
    assert.equal(isSuppressedCardImage("EB05-010"), false);
    assert.equal(isSuppressedCardImage("OP18-112"), false);
    assert.equal(isSuppressedCardImage("OP18-016"), false);
    assert.equal(isSuppressedCardImage("op18-016"), false);
    assert.equal(isSuppressedCardImage("EB05-016"), false);
    assert.equal(isSuppressedCardImage("EB05-016-P1"), false);
  });
});
