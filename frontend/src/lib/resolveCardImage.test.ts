import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import type { Metadata } from "next";
import { resolveCardImage, sitemapCardImageLoc, type ResolveCardImageOptions } from "./resolveCardImage.ts";
import { buildPageMetadata, cardJsonLd, cardSharePresentation, jsonLdScript } from "./seo.ts";

/** Fixture hashes. These ids are not read from the build manifest. */
const ALT_READY: ResolveCardImageOptions = {
  hashes: {
    "EB05-004-P1": "a1b2c3d4",
    "EB05-004-P2": "bbbbbbb2",
    "EB05-018-P2": "c3d4e5f6",
    "EB05-031-P1": "d4e5f607",
    "EB05-043-P1": "e5f60718",
    "EB05-061-P1": "b2c3d4e5",
    "OP01-001": "0123abcd",
    "OP01-001-P1": "11111111",
    "OP01-002": "abcdef01",
    "EB05-004": "99999999",
  },
};

const NO_FILES: ResolveCardImageOptions = { hashes: {} };

const IMAGE_LOC = /^https:\/\/img\.optcgassistant\.com\/[A-Za-z0-9_-]+\.png\?h=[0-9a-f]{8}$/;
const DEFAULT_IMAGE = "https://optcgassistant.com/opengraph-image";

const EMPTY_BASES = ["EB05-004", "EB05-018", "EB05-031", "EB05-043", "EB05-061"] as const;

function firstUrl(value: unknown): string {
  const first = Array.isArray(value) ? value[0] : value;
  if (!first) return "";
  if (typeof first === "string") return first;
  if (first instanceof URL) return first.toString();
  if (typeof first === "object" && first && "url" in first) {
    const url = (first as { url?: unknown }).url;
    if (typeof url === "string") return url;
    if (url instanceof URL) return url.toString();
  }
  return "";
}

function renderMetadata(id: string, imgUrl: string, options: ResolveCardImageOptions): Metadata {
  const share = cardSharePresentation({ id, img_url: imgUrl }, options);
  return buildPageMetadata({
    title: id,
    description: `${id} share image`,
    path: `https://optcgassistant.com/cards/${id}`,
    absoluteTitle: true,
    type: "article",
    images: share.images,
    twitterCard: share.twitterCard,
  });
}

function hashIsInFixture(url: string, options: ResolveCardImageOptions): boolean {
  const match = url.match(/^https:\/\/img\.optcgassistant\.com\/([A-Za-z0-9_-]+)\.png\?h=([0-9a-f]{8})$/);
  if (!match) return false;
  return options.hashes?.[match[1]] === match[2];
}

describe("card page share metadata", () => {
  for (const id of ["EB05-004", "EB05-061"] as const) {
    it(`renders a manifest image for ${id} when an alternate hash exists`, () => {
      const meta = renderMetadata(id, "", ALT_READY);
      const og = firstUrl(meta.openGraph?.images);
      const twitter = firstUrl(meta.twitter?.images);
      assert.ok(og);
      assert.equal(twitter, og);
      assert.equal(hashIsInFixture(og, ALT_READY) || og === DEFAULT_IMAGE, true);
      assert.equal(hashIsInFixture(og, ALT_READY), true);
      assert.equal(og, `https://img.optcgassistant.com/${id}-P1.png?h=${ALT_READY.hashes?.[`${id}-P1`]}`);
      assert.equal(meta.twitter?.card, "summary_large_image");

      const share = cardSharePresentation({ id, img_url: "" }, ALT_READY);
      const raw = jsonLdScript(
        cardJsonLd({
          id,
          name: id,
          description: "effect",
          imageUrl: share.jsonLdImage,
        }),
      );
      assert.match(raw, new RegExp(`${id}-P1\\.png\\?h=`));
      assert.equal(raw.includes("opengraph-image"), false);
    });

    it(`falls back to the site image for ${id} when no hash is in the fixture`, () => {
      const meta = renderMetadata(id, "", NO_FILES);
      const og = firstUrl(meta.openGraph?.images);
      assert.ok(og);
      assert.equal(hashIsInFixture(og, NO_FILES) || og === DEFAULT_IMAGE, true);
      assert.equal(og, DEFAULT_IMAGE);
      assert.equal(firstUrl(meta.twitter?.images), DEFAULT_IMAGE);
      assert.equal(meta.twitter?.card, "summary");
      const image = Array.isArray(meta.openGraph?.images) ? meta.openGraph.images[0] : meta.openGraph?.images;
      assert.equal(typeof image === "object" && image && "width" in image ? image.width : 0, 1200);
      assert.equal(typeof image === "object" && image && "height" in image ? image.height : 0, 630);

      const share = cardSharePresentation({ id, img_url: "" }, NO_FILES);
      assert.equal(share.jsonLdImage, null);
      const raw = jsonLdScript(
        cardJsonLd({
          id,
          name: id,
          description: "effect",
          imageUrl: share.jsonLdImage,
        }),
      );
      assert.equal(raw.includes('"image":'), false);
      assert.equal(raw.includes("opengraph-image"), false);
    });
  }

  it("prefers the card png over an earlier alternate, and -P1 over -P2", () => {
    const own = resolveCardImage({ id: "OP01-001", img_url: "https://example.invalid/OP01-001.png" }, ALT_READY);
    assert.equal(own?.kind, "base");
    assert.equal(own?.url, "https://img.optcgassistant.com/OP01-001.png?h=0123abcd");

    const first = resolveCardImage({ id: "EB05-004", img_url: "" }, ALT_READY);
    assert.equal(first?.kind, "parallel");
    assert.equal(first?.id, "EB05-004-P1");
  });

  it("uses -P2 when -P1 has no hash, and ignores a base hash while img_url is empty", () => {
    const second = resolveCardImage({ id: "EB05-018", img_url: "" }, ALT_READY);
    assert.equal(second?.id, "EB05-018-P2");
    assert.equal(second?.url, "https://img.optcgassistant.com/EB05-018-P2.png?h=c3d4e5f6");

    const skipped = resolveCardImage({ id: "EB05-004", card_id: "EB05-004", img_url: "" }, ALT_READY);
    assert.equal(skipped?.url.includes("/EB05-004.png"), false);
    assert.equal(skipped?.id, "EB05-004-P1");
  });
});

describe("sitemap card images", () => {
  it("emits only own png locs and skips every empty img_url", () => {
    const cards = [
      ...EMPTY_BASES.map((id) => ({ id, img_url: id === "EB05-043" ? "   " : "" })),
      { id: "OP01-001", img_url: "https://example.invalid/OP01-001.png" },
      { id: "OP01-002", img_url: "" },
    ];
    const locs = cards
      .map((card) => sitemapCardImageLoc(card, ALT_READY))
      .filter((url): url is string => Boolean(url));

    assert.deepEqual(locs, ["https://img.optcgassistant.com/OP01-001.png?h=0123abcd"]);
    for (const loc of locs) assert.match(loc, IMAGE_LOC);
    for (const id of EMPTY_BASES) {
      assert.equal(
        locs.some((loc) => loc.includes(`/${id}`)),
        false,
        id,
      );
    }
    assert.equal(locs.some((loc) => loc.includes("OP01-002")), false);
    assert.equal(locs.some((loc) => loc.includes("-P")), false);
  });
});

describe("share image call sites", () => {
  it("uses the shared resolver on the card page and only step 1 in the sitemap", () => {
    const page = readFileSync(new URL("../app/cards/[id]/page.tsx", import.meta.url), "utf8");
    const sitemap = readFileSync(new URL("../app/sitemap.ts", import.meta.url), "utf8");
    assert.equal(page.includes("cardSharePresentation"), true);
    assert.equal(page.includes("cardOgImage"), false);
    assert.equal(sitemap.includes("sitemapCardImageLoc"), true);
    assert.equal(sitemap.includes("cardOgImage"), false);
  });
});
