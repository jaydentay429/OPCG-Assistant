import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  PACKS_CDN_BASE,
  cardImagePacksUrl,
  cardImageProxyUrl,
  cardImageSources,
  cardImageUrl,
} from "./api";
import { cardOgImage } from "./seo";

const PUBLIC_BASE = PACKS_CDN_BASE || "https://img.optcgassistant.com";

describe("cardImageUrl", () => {
  it("builds one stable file URL and does not append a global version", () => {
    assert.equal(cardImageUrl("OP13-001"), `${PUBLIC_BASE}/OP13-001.png`);
    assert.equal(cardImageUrl("OP13-001-P1"), `${PUBLIC_BASE}/OP13-001-P1.png`);
    assert.equal(cardImageUrl("OP13-001-P2"), `${PUBLIC_BASE}/OP13-001-P2.png`);
    assert.equal(cardImageUrl("  "), "");
    for (const url of [cardImageUrl("OP13-001"), cardImageUrl("OP13-001-P1"), cardImageUrl("OP13-001-P2")]) {
      assert.equal(url.includes("?"), false, url);
      assert.equal(url.includes("20260927eb05v1"), false, url);
    }
  });

  it("uses that same URL for og:image and the first page image, with no declared pixel size", () => {
    const url = cardImageUrl("OP13-001");
    const og = cardOgImage("OP13-001");
    assert.ok(og);
    assert.equal(og.url, url);
    assert.equal("width" in og, false);
    assert.equal("height" in og, false);
    const sources = cardImageSources("OP13-001", url);
    assert.equal(sources[0], url);
    assert.equal(sources.filter((item) => item === url).length, 1);
    assert.equal(sources.some((item) => item.includes("?")), false);
    assert.equal(cardImagePacksUrl("OP13-001").includes("?"), false);
    assert.equal(cardImageProxyUrl("OP13-001").includes("?"), false);
    assert.equal(cardImageUrl("OP13-001-P1"), cardOgImage("OP13-001-P1")?.url);
  });
});
