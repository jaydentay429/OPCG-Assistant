import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import type { Metadata } from "next";
import {
  manifestOwnImageCount,
  resolveCardImage,
  sitemapCardImageLoc,
  type ResolveCardImageOptions,
} from "./resolveCardImage.ts";
import { sitemapCardIds } from "./parallelArts.ts";
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

  it("uses -P2 when -P1 has no hash", () => {
    const second = resolveCardImage({ id: "EB05-018", img_url: "" }, ALT_READY);
    assert.equal(second?.id, "EB05-018-P2");
    assert.equal(second?.url, "https://img.optcgassistant.com/EB05-018-P2.png?h=c3d4e5f6");
  });

  it("uses the card's own png when img_url is empty but the manifest has its hash", () => {
    const hashes = {
      "OP18-046": "87040af3",
      "EB05-016": "9f53b217",
      "EB05-016-P1": "f0de3b59",
    };
    const options = { hashes };
    const own = resolveCardImage({ id: "OP18-046", img_url: "" }, options);
    assert.equal(own?.kind, "base");
    assert.equal(own?.url, "https://img.optcgassistant.com/OP18-046.png?h=87040af3");
    const meta = renderMetadata("OP18-046", "", options);
    assert.equal(firstUrl(meta.openGraph?.images), own?.url);
    assert.equal(meta.twitter?.card, "summary_large_image");

    const base = resolveCardImage({ id: "EB05-016", img_url: "" }, options);
    assert.equal(base?.kind, "base");
    assert.equal(base?.url, "https://img.optcgassistant.com/EB05-016.png?h=9f53b217");
    assert.equal(sitemapCardImageLoc({ id: "EB05-016", img_url: "" }, options), base?.url);
    assert.equal(sitemapCardImageLoc({ id: "OP18-046", img_url: "" }, options), own?.url);
  });
});

describe("sitemap card images", () => {
  it("emits an own png when the manifest has a hash, including an empty img_url", () => {
    const cards = [
      ...EMPTY_BASES.map((id) => ({ id, img_url: id === "EB05-043" ? "   " : "" })),
      { id: "OP01-001", img_url: "https://example.invalid/OP01-001.png" },
      { id: "OP01-002", img_url: "" },
    ];
    const locs = cards
      .map((card) => sitemapCardImageLoc(card, ALT_READY))
      .filter((url): url is string => Boolean(url));

    assert.deepEqual(locs, [
      "https://img.optcgassistant.com/OP01-001.png?h=0123abcd",
      "https://img.optcgassistant.com/OP01-002.png?h=abcdef01",
    ]);
    for (const loc of locs) assert.match(loc, IMAGE_LOC);
    for (const id of EMPTY_BASES) {
      assert.equal(
        locs.some((loc) => loc.includes(`/${id}.png`) || loc.includes(`/${id}-`)),
        false,
        id,
      );
    }
    assert.equal(locs.some((loc) => loc.includes("-P")), false);
    const floor = manifestOwnImageCount(
      cards.map((card) => card.id),
      ALT_READY,
    );
    assert.equal(locs.length, floor);
    assert.ok(locs.length >= floor);
  });
});

describe("share image call sites", () => {
  it("uses the shared resolver on the card page and only step 1 in the sitemap", () => {
    const page = readFileSync(new URL("../app/cards/[id]/page.tsx", import.meta.url), "utf8");
    const sitemap = readFileSync(new URL("../app/sitemap.ts", import.meta.url), "utf8");
    assert.equal(page.includes("cardSharePresentation"), true);
    assert.equal(page.includes("cardOgImage"), false);
    assert.equal(sitemap.includes("sitemapCardImageLoc"), true);
    assert.equal(sitemap.includes("manifestOwnImageCount"), true);
    assert.equal(sitemap.includes("cardOgImage"), false);
    assert.equal(sitemap.includes("loadIdsWithImgUrl"), false);
    assert.equal(readFileSync(new URL("./resolveCardImage.ts", import.meta.url), "utf8").includes("hasPrintedImageUrl"), false);
  });
});

/** Own hashes that #47 dropped because img_url was empty. From the SEO lost-images list. */
const RESTORED_OWN: Record<string, string> = {
  "EB05-001": "bc18eac0",
  "EB05-002": "90bace17",
  "EB05-005": "ce17385f",
  "EB05-006": "ab6142c0",
  "EB05-007": "78e4e975",
  "EB05-009": "c4ddd776",
  "EB05-011": "ce22b922",
  "EB05-012": "a7163064",
  "EB05-013": "e65f04bb",
  "EB05-014": "db550b8d",
  "EB05-016": "9f53b217",
  "EB05-017": "88c3d15d",
  "EB05-019": "1f343cf5",
  "EB05-020": "9eaa5bd3",
  "EB05-021": "29938dbd",
  "EB05-022": "338e7039",
  "EB05-025": "e9ff1e42",
  "EB05-027": "28c27877",
  "EB05-028": "eb506966",
  "EB05-029": "11ac57eb",
  "EB05-030": "3ae3a876",
  "EB05-034": "ca922702",
  "EB05-035": "b846befd",
  "EB05-037": "1e788ad4",
  "EB05-038": "2c1d4699",
  "EB05-044": "20434612",
  "EB05-045": "fc9e5287",
  "EB05-046": "92194e1d",
  "EB05-047": "2629cb4a",
  "EB05-049": "b5ea7367",
  "EB05-051": "31a323a9",
  "EB05-052": "e6f68c54",
  "EB05-054": "c6d1a4f5",
  "EB05-055": "fc4a968a",
  "EB05-057": "329f4963",
  "OP18-011": "f2841823",
  "OP18-016": "cb8ad5a3",
  "OP18-017": "abff0bb2",
  "OP18-024": "7fe8d483",
  "OP18-025": "136e365c",
  "OP18-034": "ea77f66d",
  "OP18-044": "274c36d9",
  "OP18-046": "87040af3",
  "OP18-048": "cb631e29",
  "OP18-055": "6128a24a",
  "OP18-061": "3997b7fe",
  "OP18-076": "a09c5157",
  "OP18-084": "20c807fd",
  "OP18-089": "02533aad",
  "OP18-100": "bd42c112",
  "OP18-106": "c6bb3598",
  "OP18-112": "518a7f4a",
  "OP18-113": "a14a6072",
  "P-160": "aee899d7",
};

/** Parallel hashes that replaced the base image while img_url was empty. */
const RESTORED_PARALLEL: Record<string, string> = {
  "EB05-001-P1": "fbcc3f94",
  "EB05-006-P1": "5f4ab12c",
  "EB05-014-P1": "6df375e2",
  "EB05-016-P1": "f0de3b59",
  "EB05-021-P1": "1fda7a80",
  "EB05-028-P1": "75c18e9a",
  "EB05-034-P1": "f7fe5420",
  "EB05-037-P1": "2d8cc0e9",
  "EB05-046-P1": "979d592e",
  "EB05-052-P1": "e133041f",
  "EB05-055-P1": "8d71991d",
  "EB05-057-P1": "efaf1c59",
};

describe("cards dropped by the img_url gate", () => {
  const options: ResolveCardImageOptions = {
    hashes: { ...RESTORED_OWN, ...RESTORED_PARALLEL },
  };

  it("restores every lost card to its own png, not a parallel or the site image", () => {
    const ids = Object.keys(RESTORED_OWN);
    assert.equal(ids.length, 54);
    const locs: string[] = [];
    for (const id of ids) {
      const resolved = resolveCardImage({ id, img_url: "" }, options);
      const expected = `https://img.optcgassistant.com/${id}.png?h=${RESTORED_OWN[id]}`;
      assert.equal(resolved?.kind, "base", id);
      assert.equal(resolved?.url, expected, id);
      const meta = renderMetadata(id, "", options);
      assert.equal(firstUrl(meta.openGraph?.images), expected, id);
      assert.equal(firstUrl(meta.twitter?.images), expected, id);
      assert.equal(meta.twitter?.card, "summary_large_image", id);
      const share = cardSharePresentation({ id, img_url: "" }, options);
      assert.equal(share.jsonLdImage, expected, id);
      const loc = sitemapCardImageLoc({ id, img_url: "" }, options);
      assert.equal(loc, expected, id);
      if (loc) locs.push(loc);
    }
    const floor = manifestOwnImageCount(ids, options);
    assert.equal(locs.length, 54);
    assert.equal(floor, 54);
    assert.ok(locs.length >= floor);
  });
});

describe("sitemap image floor", () => {
  it("counts one image:loc for every non-parallel manifest hash in the card list", () => {
    const ids = sitemapCardIds(
      JSON.parse(readFileSync(new URL("../generated/card-ids.json", import.meta.url), "utf8")) as string[],
    );
    const manifest = JSON.parse(
      readFileSync(new URL("../generated/card-image-manifest.json", import.meta.url), "utf8"),
    ) as Record<string, string>;
    const options = { hashes: manifest };
    const floor = manifestOwnImageCount(ids, options);
    let emitted = 0;
    for (const id of ids) {
      if (sitemapCardImageLoc({ id, img_url: "" }, options)) emitted += 1;
    }
    assert.ok(floor > 0);
    assert.equal(emitted, floor);
    assert.ok(emitted >= floor);
  });
});
