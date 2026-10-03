import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, it } from "node:test";
import {
  PACKS_CDN_BASE,
  cardImagePacksUrl,
  cardImageProxyUrl,
  cardImageSources,
  cardImageUrl,
  hasCardImage,
  stripAbsentCardImageUrls,
} from "./api";
import { cardImageHash } from "./cardImageManifest";
import { cardOgImage } from "./seo";

const PUBLIC_BASE = PACKS_CDN_BASE || "https://img.optcgassistant.com";

function runManifestCheck(body: string, minCount?: string) {
  const dir = mkdtempSync(join(tmpdir(), "card-manifest-"));
  const file = join(dir, "card-image-manifest.json");
  writeFileSync(file, body);
  const env: NodeJS.ProcessEnv = { ...process.env, CARD_IMAGE_MANIFEST: file };
  if (minCount != null) env.CARD_IMAGE_MANIFEST_MIN_COUNT = minCount;
  return spawnSync(process.execPath, ["scripts/check-card-image-manifest.mjs"], {
    cwd: process.cwd(),
    env,
    encoding: "utf8",
  });
}

describe("cardImageUrl", () => {
  it("appends the manifest content hash and uses one URL for every public surface", () => {
    const url = `${PUBLIC_BASE}/OP13-001.png?h=870e05eb`;
    assert.equal(cardImageHash("OP13-001"), "870e05eb");
    assert.equal(cardImageHash("op13-001"), "870e05eb");
    assert.equal(hasCardImage("OP13-001"), true);
    assert.equal(cardImageUrl("OP13-001"), url);
    assert.equal(cardImageUrl("OP13-001-P1").startsWith(`${PUBLIC_BASE}/OP13-001-P1.png?h=`), true);
    assert.equal(cardImageUrl("OP13-001-P2").startsWith(`${PUBLIC_BASE}/OP13-001-P2.png?h=`), true);
    assert.match(cardImageUrl("OP13-001-P1"), /\?h=[0-9a-f]{8}$/);
    assert.equal(cardImageUrl("  "), "");
    assert.equal(cardImageUrl("OP13-001").includes("20260927eb05v1"), false);

    const og = cardOgImage("OP13-001");
    assert.ok(og);
    assert.equal(og.url, url);
    assert.equal("width" in og, false);
    assert.equal("height" in og, false);
    const sources = cardImageSources("OP13-001", "https://example.invalid/local.png");
    assert.deepEqual(sources, [url]);
    assert.equal(cardImageUrl("OP13-001-P1"), cardOgImage("OP13-001-P1")?.url);
    assert.equal(cardImageHash("EB05-048"), "f7a50a1d");
    assert.equal(cardImageUrl("EB05-048"), `${PUBLIC_BASE}/EB05-048.png?h=f7a50a1d`);
    assert.equal(cardImageHash("EB05-046"), "92194e1d");
    assert.equal(cardImageUrl("EB05-046"), `${PUBLIC_BASE}/EB05-046.png?h=92194e1d`);
    assert.equal(cardImageHash("EB05-016"), "9f53b217");
    assert.equal(cardImageUrl("EB05-016"), `${PUBLIC_BASE}/EB05-016.png?h=9f53b217`);
    assert.equal(cardOgImage("EB05-016")?.url, `${PUBLIC_BASE}/EB05-016.png?h=9f53b217`);
    assert.equal(cardImageHash("EB05-016-P1"), "f0de3b59");
    assert.equal(cardImageUrl("EB05-016-P1"), `${PUBLIC_BASE}/EB05-016-P1.png?h=f0de3b59`);
    assert.equal(cardOgImage("EB05-016-P1")?.url, `${PUBLIC_BASE}/EB05-016-P1.png?h=f0de3b59`);
    assert.equal(cardImageHash("OP18-016"), "cb8ad5a3");
    assert.equal(cardImageUrl("OP18-016"), `${PUBLIC_BASE}/OP18-016.png?h=cb8ad5a3`);
    assert.equal(cardOgImage("OP18-016")?.url, `${PUBLIC_BASE}/OP18-016.png?h=cb8ad5a3`);
    assert.equal(cardImageHash("OP18-025"), "136e365c");
    assert.equal(cardImageUrl("OP18-025"), `${PUBLIC_BASE}/OP18-025.png?h=136e365c`);
    assert.equal(cardOgImage("OP18-025")?.url, `${PUBLIC_BASE}/OP18-025.png?h=136e365c`);
    assert.equal(cardImageHash("OP18-044"), "274c36d9");
    assert.equal(cardImageUrl("OP18-044"), `${PUBLIC_BASE}/OP18-044.png?h=274c36d9`);
    assert.equal(cardOgImage("OP18-044")?.url, `${PUBLIC_BASE}/OP18-044.png?h=274c36d9`);
    assert.equal(cardImageHash("OP18-076"), "a09c5157");
    assert.equal(cardImageUrl("OP18-076"), `${PUBLIC_BASE}/OP18-076.png?h=a09c5157`);
    assert.equal(cardOgImage("OP18-076")?.url, `${PUBLIC_BASE}/OP18-076.png?h=a09c5157`);
    assert.equal(cardImageHash("OP18-089"), "02533aad");
    assert.equal(cardImageUrl("OP18-089"), `${PUBLIC_BASE}/OP18-089.png?h=02533aad`);
    assert.equal(cardOgImage("OP18-089")?.url, `${PUBLIC_BASE}/OP18-089.png?h=02533aad`);
    assert.equal(cardImageHash("P-160"), "aee899d7");
    assert.equal(cardImageUrl("P-160"), `${PUBLIC_BASE}/P-160.png?h=aee899d7`);
    assert.equal(cardOgImage("P-160")?.url, `${PUBLIC_BASE}/P-160.png?h=aee899d7`);
    assert.equal(cardImageHash("OP18-106"), "c6bb3598");
    assert.equal(cardImageUrl("OP18-106"), `${PUBLIC_BASE}/OP18-106.png?h=c6bb3598`);
    assert.equal(cardOgImage("OP18-106")?.url, `${PUBLIC_BASE}/OP18-106.png?h=c6bb3598`);
    assert.equal(cardImageHash("EB05-049"), "b5ea7367");
    assert.equal(cardImageUrl("EB05-049"), `${PUBLIC_BASE}/EB05-049.png?h=b5ea7367`);
    assert.equal(cardOgImage("EB05-049")?.url, `${PUBLIC_BASE}/EB05-049.png?h=b5ea7367`);
  });

  it("returns no URL and no og image when the manifest has no file", () => {
    for (const id of ["OP18-112", "OP16-098-P2"]) {
      assert.equal(hasCardImage(id), false);
      assert.equal(cardImageHash(id), "");
      assert.equal(cardImageUrl(id), "");
      assert.equal(cardOgImage(id), null);
      assert.deepEqual(cardImageSources(id, `${PUBLIC_BASE}/${id}.png`), []);
      const stripped = stripAbsentCardImageUrls({
        img_local_url: `${PUBLIC_BASE}/${id}.png`,
        img_url: `https://example.invalid/${id}.png`,
        img_full_url: "",
        alt_image_urls: [`${PUBLIC_BASE}/${id}.png`],
      });
      assert.equal(stripped.img_local_url, null);
      assert.equal(stripped.img_url, null);
      assert.deepEqual(stripped.alt_image_urls, []);
      const proxy = stripAbsentCardImageUrls({
        img_local_url: `https://api.optcgassistant.com/images/card/${id}`,
        img_url: `https://api.optcgassistant.com/packs/${id}.png`,
        alt_image_urls: [`https://api.optcgassistant.com/images/card/${id}`],
      });
      assert.equal(proxy.img_local_url, null);
      assert.equal(proxy.img_url, null);
      assert.deepEqual(proxy.alt_image_urls, []);
    }
    const kept = stripAbsentCardImageUrls({
      img_local_url: `${PUBLIC_BASE}/OP13-001.png`,
      img_url: "https://api.optcgassistant.com/images/card/OP13-001",
      alt_image_urls: [`${PUBLIC_BASE}/OP13-001-P1.png`],
    });
    assert.equal(kept.img_local_url, `${PUBLIC_BASE}/OP13-001.png`);
    assert.equal(kept.img_url, "https://api.optcgassistant.com/images/card/OP13-001");
    assert.deepEqual(kept.alt_image_urls, [`${PUBLIC_BASE}/OP13-001-P1.png`]);
    assert.equal(cardImagePacksUrl("OP13-001").includes("?"), false);
    assert.equal(cardImageProxyUrl("OP13-001").includes("?"), false);
  });

  it("fails the build check on an empty or undersized manifest", () => {
    const empty = runManifestCheck("{}\n");
    assert.notEqual(empty.status, 0);
    assert.match(empty.stderr, /empty/);

    const missing = spawnSync(process.execPath, ["scripts/check-card-image-manifest.mjs"], {
      cwd: process.cwd(),
      env: { ...process.env, CARD_IMAGE_MANIFEST: join(tmpdir(), "no-such-card-manifest.json") },
      encoding: "utf8",
    });
    assert.notEqual(missing.status, 0);

    const under = runManifestCheck('{"OP13-001":"870e05eb"}\n', "2");
    assert.notEqual(under.status, 0);
    assert.match(under.stderr, /floor/);

    const ok = runManifestCheck('{"OP13-001":"870e05eb"}\n', "1");
    assert.equal(ok.status, 0, ok.stderr);
  });
});
