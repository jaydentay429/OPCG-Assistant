import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { hasCardImage } from "./api";
import { isSuppressedCardImage } from "./cardImagePolicy";

describe("isSuppressedCardImage", () => {
  it("follows the manifest and ignores card-data image fields", () => {
    assert.equal(hasCardImage("EB05-046"), false);
    assert.equal(isSuppressedCardImage("EB05-046"), true);
    assert.equal(isSuppressedCardImage("eb05-046"), true);
    assert.equal(hasCardImage("OP18-112"), false);
    assert.equal(isSuppressedCardImage("OP18-112"), true);
    assert.equal(hasCardImage("OP16-098-P2"), false);
    assert.equal(isSuppressedCardImage("OP16-098-P2"), true);
    assert.equal(hasCardImage("EB05-048"), true);
    assert.equal(isSuppressedCardImage("EB05-048"), false);
    assert.equal(hasCardImage("EB05-010"), true);
    assert.equal(isSuppressedCardImage("EB05-010"), false);
    assert.equal(isSuppressedCardImage(""), false);
    assert.equal(isSuppressedCardImage("  "), false);
  });
});
