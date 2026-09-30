import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { PACKS_CDN_BASE, cardImageUrl } from "./api";
import {
  CARD_WALL_IMAGE_SIZES,
  cardWebpObjectKey,
  clearListWebpMisses,
  listCardImageAttrs,
  noteListWebpMiss,
} from "./cardImageSrcSet";

const PUBLIC_BASE = PACKS_CDN_BASE || "https://img.optcgassistant.com";

describe("list card webp srcset", () => {
  it("points the card wall at hashed thumbnails and falls back to the png url", () => {
    clearListWebpMisses();
    const hash = "870e05eb";
    const png = `${PUBLIC_BASE}/OP13-001.png?h=${hash}`;
    assert.equal(cardImageUrl("OP13-001"), png);
    assert.equal(cardWebpObjectKey("op13-001", hash, "w200"), `OP13-001.w200.${hash}.webp`);
    assert.equal(cardWebpObjectKey("OP13-001", hash, "w320"), `OP13-001.w320.${hash}.webp`);
    assert.equal(cardWebpObjectKey("OP13-001", hash, "full"), `OP13-001.${hash}.webp`);

    const webp = listCardImageAttrs("OP13-001");
    assert.ok(webp);
    assert.equal(webp.webp, true);
    assert.equal(webp.src, `${PUBLIC_BASE}/OP13-001.w320.${hash}.webp?h=${hash}`);
    assert.equal(
      webp.srcSet,
      `${PUBLIC_BASE}/OP13-001.w200.${hash}.webp?h=${hash} 200w, ${PUBLIC_BASE}/OP13-001.w320.${hash}.webp?h=${hash} 320w`,
    );
    assert.equal(webp.sizes, CARD_WALL_IMAGE_SIZES);
    const srcSet = webp.srcSet ?? "";
    assert.equal(srcSet.includes(`OP13-001.${hash}.webp`), false);
    assert.equal(webp.sizes, "(max-width: 900px) 60px, 153px");

    const failed = listCardImageAttrs("OP13-001", true);
    assert.deepEqual(failed, { src: png, webp: false });
    assert.equal(failed?.srcSet, undefined);

    noteListWebpMiss("op13-001");
    const remembered = listCardImageAttrs("OP13-001");
    assert.deepEqual(remembered, { src: png, webp: false });

    clearListWebpMisses();
    const again = listCardImageAttrs("OP13-001");
    assert.equal(again?.webp, true);
  });

  it("returns nothing when the manifest has no png hash", () => {
    clearListWebpMisses();
    assert.equal(cardImageUrl("OP18-112"), "");
    assert.equal(listCardImageAttrs("OP18-112"), null);
    assert.equal(listCardImageAttrs("OP18-112", true), null);
    noteListWebpMiss("OP18-112");
    assert.equal(listCardImageAttrs("OP18-112"), null);
  });
});
