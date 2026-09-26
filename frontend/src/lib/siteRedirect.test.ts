import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { CANONICAL_ORIGIN, canonicalRedirect, siteAbsoluteUrl } from "./siteRedirect";

describe("canonicalRedirect", () => {
  it("301s a lowercase card id to uppercase and keeps the query", () => {
    const plan = canonicalRedirect("/cards/op01-065", "?ref=deck&x=1");
    assert.deepEqual(plan, {
      status: 301,
      location: `${CANONICAL_ORIGIN}/cards/OP01-065?ref=deck&x=1`,
    });
  });

  it("301s mixed-case parallel and promo ids, including a trailing slash, in one hop", () => {
    assert.equal(canonicalRedirect("/cards/st18-005-p2/")?.status, 301);
    assert.equal(
      canonicalRedirect("/cards/st18-005-p2/", "?picked=1")?.location,
      `${CANONICAL_ORIGIN}/cards/ST18-005-P2?picked=1`,
    );
    assert.equal(canonicalRedirect("/cards/p-001")?.location, `${CANONICAL_ORIGIN}/cards/P-001`);
  });

  it("leaves canonical card URLs alone, including ST18-005-P2 and P-001", () => {
    for (const path of ["/cards/OP01-065", "/cards/ST18-005-P2", "/cards/P-001"]) {
      assert.equal(canonicalRedirect(path, "?q=1"), null, path);
    }
  });

  it("308s trailing slashes on other routes and keeps the query", () => {
    assert.deepEqual(canonicalRedirect("/search/", "?q=luffy"), {
      status: 308,
      location: `${CANONICAL_ORIGIN}/search?q=luffy`,
    });
    assert.deepEqual(canonicalRedirect("/sets/"), {
      status: 308,
      location: `${CANONICAL_ORIGIN}/sets`,
    });
    assert.equal(canonicalRedirect("/"), null);
    assert.equal(canonicalRedirect("/search"), null);
  });

  it("never puts the request host into Location", () => {
    const samples = [
      siteAbsoluteUrl("/cards/OP01-065", "?a=1"),
      canonicalRedirect("/cards/op01-065", "?a=1")?.location,
      canonicalRedirect("/search/")?.location,
      canonicalRedirect("/sets/")?.location,
    ];
    for (const location of samples) {
      assert.equal(location?.startsWith(`${CANONICAL_ORIGIN}/`), true, location);
      assert.equal(location?.includes("localhost"), false, location);
      assert.equal(location?.includes(":3000"), false, location);
    }
  });
});
