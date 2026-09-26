import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  CANONICAL_ORIGIN,
  PUBLIC_SITE_ORIGIN,
  canonicalOriginFrom,
  canonicalRedirect,
  siteAbsoluteUrl,
} from "./siteRedirect";

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

  it("does not redirect card ids that need percent-encoding", () => {
    assert.equal(canonicalRedirect("/cards/OP01%20065"), null);
    assert.equal(canonicalRedirect("/cards/OP01%20065", "?q=1"), null);
    assert.equal(canonicalRedirect("/cards/%E8%B7%AF%E9%A3%9E"), null);
    assert.equal(canonicalRedirect("/cards/OP01%2F065"), null);
    assert.equal(canonicalRedirect("/cards/OP01 065"), null);
  });

  it("308s a trailing slash off an unsafe card id without case-folding", () => {
    assert.deepEqual(canonicalRedirect("/cards/OP01%20065/"), {
      status: 308,
      location: `${CANONICAL_ORIGIN}/cards/OP01%20065`,
    });
    assert.deepEqual(canonicalRedirect("/cards/%E8%B7%AF%E9%A3%9E/", "?q=1"), {
      status: 308,
      location: `${CANONICAL_ORIGIN}/cards/%E8%B7%AF%E9%A3%9E?q=1`,
    });
  });

  it("never redirects a second time (no loop)", () => {
    const samples: Array<[string, string]> = [
      ["/cards/op01-065", ""],
      ["/cards/op01-065/", ""],
      ["/cards/st18-005-p2/", "?picked=1"],
      ["/cards/op01-065", "?ref=deck&x=1"],
      ["/cards/OP01-065", ""],
      ["/cards/OP01%20065", ""],
      ["/cards/OP01%20065/", ""],
      ["/cards/%E8%B7%AF%E9%A3%9E", ""],
      ["/cards/%E8%B7%AF%E9%A3%9E/", "?q=1"],
      ["/search/", ""],
      ["/search/", "?q=luffy"],
      ["/sets/", ""],
      ["/cards/OP01%2F065", ""],
      ["/cards/OP01%2F065/", ""],
      ["/foo%2Fbar/", "?x=1"],
    ];
    for (const [pathname, search] of samples) {
      const plan = canonicalRedirect(pathname, search);
      if (!plan) continue;
      const url = new URL(plan.location);
      assert.equal(
        canonicalRedirect(url.pathname, url.search),
        null,
        `${pathname}${search} -> ${url.pathname}${url.search}`,
      );
    }
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

describe("canonicalOriginFrom", () => {
  it("uses the public site when the env value is missing or local", () => {
    assert.equal(canonicalOriginFrom(undefined), PUBLIC_SITE_ORIGIN);
    assert.equal(canonicalOriginFrom(null), PUBLIC_SITE_ORIGIN);
    assert.equal(canonicalOriginFrom(""), PUBLIC_SITE_ORIGIN);
    assert.equal(canonicalOriginFrom("   "), PUBLIC_SITE_ORIGIN);
    assert.equal(canonicalOriginFrom("https://optcgassistant.com"), PUBLIC_SITE_ORIGIN);
    assert.equal(canonicalOriginFrom("https://optcgassistant.com/"), PUBLIC_SITE_ORIGIN);
    assert.equal(canonicalOriginFrom("http://localhost:3000"), PUBLIC_SITE_ORIGIN);
    assert.equal(canonicalOriginFrom("https://localhost"), PUBLIC_SITE_ORIGIN);
    assert.equal(canonicalOriginFrom("http://127.0.0.1:3000"), PUBLIC_SITE_ORIGIN);
    assert.equal(canonicalOriginFrom("https://127.0.0.1"), PUBLIC_SITE_ORIGIN);
    assert.equal(CANONICAL_ORIGIN.includes("localhost"), false);
    assert.equal(CANONICAL_ORIGIN.includes("127.0.0.1"), false);
  });
});
