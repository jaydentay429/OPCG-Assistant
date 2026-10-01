import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { PACKS_CDN_BASE, cardImageUrl } from "./api";
import { cardJsonLd, cardOgImage, jsonLdScript } from "./seo";
import {
  CARD_WALL_IMAGE_SIZES,
  DETAIL_THUMB_IMAGE_SIZES,
  cardWebpObjectKey,
  clearHeroWebpMisses,
  clearListWebpMisses,
  heroCardImageAttrs,
  heroPreloadHref,
  listCardImageAttrs,
  noteHeroWebpMiss,
  noteListWebpMiss,
  prefetchHeroImage,
  webpLoadAlreadyFailed,
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

  it("uses thumbnail webp for the detail strip sizes and still omits the full-size key", () => {
    clearListWebpMisses();
    const hash = "870e05eb";
    const thumb = listCardImageAttrs("OP13-001", false, DETAIL_THUMB_IMAGE_SIZES);
    assert.ok(thumb);
    assert.equal(thumb.webp, true);
    assert.equal(thumb.sizes, "80px");
    assert.equal(DETAIL_THUMB_IMAGE_SIZES, "80px");
    assert.match(thumb.srcSet ?? "", /OP13-001\.w200\.870e05eb\.webp/);
    assert.match(thumb.srcSet ?? "", /OP13-001\.w320\.870e05eb\.webp/);
    assert.equal((thumb.srcSet ?? "").includes(`OP13-001.${hash}.webp`), false);
    assert.equal(thumb.src.includes(`OP13-001.${hash}.webp`), false);
    assert.equal(thumb.src.endsWith(".png?h=870e05eb"), false);
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

describe("card page hero webp", () => {
  it("requests the full-size webp and falls back to the same png url", () => {
    clearHeroWebpMisses();
    clearListWebpMisses();
    const hash = "870e05eb";
    const png = `${PUBLIC_BASE}/OP13-001.png?h=${hash}`;
    const webpUrl = `${PUBLIC_BASE}/OP13-001.${hash}.webp?h=${hash}`;
    const hero = heroCardImageAttrs("OP13-001");
    assert.ok(hero);
    assert.equal(hero.webp, true);
    assert.equal(hero.src, webpUrl);
    assert.equal(hero.srcSet, undefined);
    assert.equal(heroPreloadHref("op13-001"), webpUrl);

    const failed = heroCardImageAttrs("OP13-001", true);
    assert.deepEqual(failed, { src: png, webp: false });

    noteHeroWebpMiss("op13-001");
    assert.deepEqual(heroCardImageAttrs("OP13-001"), { src: png, webp: false });
    assert.equal(listCardImageAttrs("OP13-001")?.webp, true);

    clearHeroWebpMisses();
    noteListWebpMiss("OP13-001");
    assert.equal(heroCardImageAttrs("OP13-001")?.src, webpUrl);
    clearListWebpMisses();
  });

  it("keeps a variant on its own hash and leaves og/json-ld on the png", () => {
    clearHeroWebpMisses();
    const hash = "a1625823";
    const png = `${PUBLIC_BASE}/OP13-001-P1.png?h=${hash}`;
    const hero = heroCardImageAttrs("OP13-001-P1");
    assert.equal(hero?.src, `${PUBLIC_BASE}/OP13-001-P1.${hash}.webp?h=${hash}`);
    assert.equal(heroPreloadHref("OP13-001-P1"), hero?.src);
    assert.equal(cardImageUrl("OP13-001-P1"), png);
    const og = cardOgImage("OP13-001-P1");
    assert.equal(og?.url, png);
    const raw = jsonLdScript(
      cardJsonLd({
        id: "OP13-001-P1",
        name: "variant",
        description: "d",
        imageUrl: og?.url,
      }),
    );
    assert.match(raw, /OP13-001-P1\.png\?h=a1625823/);
    assert.equal(raw.includes(".webp"), false);
  });

  it("returns nothing when the manifest has no png hash", () => {
    assert.equal(heroCardImageAttrs("OP18-112"), null);
    assert.equal(heroCardImageAttrs("OP18-112", true), null);
    assert.equal(heroPreloadHref("OP18-112"), "");
    assert.equal(cardOgImage("OP18-112"), null);
  });

  it("treats an image that already failed before mount as a miss", () => {
    assert.equal(webpLoadAlreadyFailed(null), false);
    assert.equal(webpLoadAlreadyFailed(undefined), false);
    assert.equal(webpLoadAlreadyFailed({ complete: false, naturalWidth: 0 }), false);
    assert.equal(webpLoadAlreadyFailed({ complete: true, naturalWidth: 600 }), false);
    assert.equal(webpLoadAlreadyFailed({ complete: true, naturalWidth: 0 }), true);
  });

  it("skips hero prefetch when there is no browser", () => {
    assert.equal(typeof window, "undefined");
    prefetchHeroImage("OP13-001");
    prefetchHeroImage("OP13-001-P1");
  });
});
