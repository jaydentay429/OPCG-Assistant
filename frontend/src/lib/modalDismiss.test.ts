import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { BACKDROP_DISMISS_GRACE_MS, shouldIgnoreBackdropDismiss } from "./modalDismiss.ts";

describe("backdrop dismiss grace", () => {
  it("ignores a backdrop click in the first 400ms and still allows one after that", () => {
    const openedAt = 1_000;
    assert.equal(BACKDROP_DISMISS_GRACE_MS, 400);
    assert.equal(shouldIgnoreBackdropDismiss(openedAt, openedAt + 16), true);
    assert.equal(shouldIgnoreBackdropDismiss(openedAt, openedAt + 344), true);
    assert.equal(shouldIgnoreBackdropDismiss(openedAt, openedAt + 399), true);
    assert.equal(shouldIgnoreBackdropDismiss(openedAt, openedAt + 400), false);
    assert.equal(shouldIgnoreBackdropDismiss(openedAt, openedAt + 500), false);
  });
});