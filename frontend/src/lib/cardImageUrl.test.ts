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
    assert.equal(cardImageHash("EB05-048"), "3609c45f");
    assert.equal(cardImageUrl("EB05-048"), `${PUBLIC_BASE}/EB05-048.png?h=3609c45f`);
    assert.equal(cardImageHash("EB05-046"), "aefd558d");
    assert.equal(cardImageUrl("EB05-046"), `${PUBLIC_BASE}/EB05-046.png?h=aefd558d`);
    assert.equal(cardImageHash("EB05-016"), "e22c4713");
    assert.equal(cardImageUrl("EB05-016"), `${PUBLIC_BASE}/EB05-016.png?h=e22c4713`);
    assert.equal(cardOgImage("EB05-016")?.url, `${PUBLIC_BASE}/EB05-016.png?h=e22c4713`);
    assert.equal(cardImageHash("EB05-016-P1"), "f0de3b59");
    assert.equal(cardImageUrl("EB05-016-P1"), `${PUBLIC_BASE}/EB05-016-P1.png?h=f0de3b59`);
    assert.equal(cardOgImage("EB05-016-P1")?.url, `${PUBLIC_BASE}/EB05-016-P1.png?h=f0de3b59`);
    assert.equal(cardImageHash("OP18-016"), "f8a0b4f1");
    assert.equal(cardImageUrl("OP18-016"), `${PUBLIC_BASE}/OP18-016.png?h=f8a0b4f1`);
    assert.equal(cardOgImage("OP18-016")?.url, `${PUBLIC_BASE}/OP18-016.png?h=f8a0b4f1`);
    assert.equal(cardImageHash("OP18-025"), "7b3339d7");
    assert.equal(cardImageUrl("OP18-025"), `${PUBLIC_BASE}/OP18-025.png?h=7b3339d7`);
    assert.equal(cardOgImage("OP18-025")?.url, `${PUBLIC_BASE}/OP18-025.png?h=7b3339d7`);
    assert.equal(cardImageHash("OP18-044"), "972a0578");
    assert.equal(cardImageUrl("OP18-044"), `${PUBLIC_BASE}/OP18-044.png?h=972a0578`);
    assert.equal(cardOgImage("OP18-044")?.url, `${PUBLIC_BASE}/OP18-044.png?h=972a0578`);
    assert.equal(cardImageHash("OP18-085"), "7a8857b3");
    assert.equal(cardImageUrl("OP18-085"), `${PUBLIC_BASE}/OP18-085.png?h=7a8857b3`);
    assert.equal(cardOgImage("OP18-085")?.url, `${PUBLIC_BASE}/OP18-085.png?h=7a8857b3`);
    assert.equal(cardImageHash("OP18-010"), "2d003704");
    assert.equal(cardImageUrl("OP18-010"), `${PUBLIC_BASE}/OP18-010.png?h=2d003704`);
    assert.equal(cardOgImage("OP18-010")?.url, `${PUBLIC_BASE}/OP18-010.png?h=2d003704`);
    assert.equal(cardImageHash("OP18-032"), "e40e9646");
    assert.equal(cardImageUrl("OP18-032"), `${PUBLIC_BASE}/OP18-032.png?h=e40e9646`);
    assert.equal(cardOgImage("OP18-032")?.url, `${PUBLIC_BASE}/OP18-032.png?h=e40e9646`);
    assert.equal(cardImageHash("OP18-052"), "5ba5ebfa");
    assert.equal(cardImageUrl("OP18-052"), `${PUBLIC_BASE}/OP18-052.png?h=5ba5ebfa`);
    assert.equal(cardOgImage("OP18-052")?.url, `${PUBLIC_BASE}/OP18-052.png?h=5ba5ebfa`);
    assert.equal(cardImageHash("OP18-063"), "9edd6b85");
    assert.equal(cardImageUrl("OP18-063"), `${PUBLIC_BASE}/OP18-063.png?h=9edd6b85`);
    assert.equal(cardOgImage("OP18-063")?.url, `${PUBLIC_BASE}/OP18-063.png?h=9edd6b85`);
    assert.equal(cardImageHash("OP18-069"), "ddbfcdc4");
    assert.equal(cardImageUrl("OP18-069"), `${PUBLIC_BASE}/OP18-069.png?h=ddbfcdc4`);
    assert.equal(cardOgImage("OP18-069")?.url, `${PUBLIC_BASE}/OP18-069.png?h=ddbfcdc4`);
    assert.equal(cardImageHash("OP18-091"), "d2c97273");
    assert.equal(cardImageUrl("OP18-091"), `${PUBLIC_BASE}/OP18-091.png?h=d2c97273`);
    assert.equal(cardOgImage("OP18-091")?.url, `${PUBLIC_BASE}/OP18-091.png?h=d2c97273`);
    assert.equal(cardImageHash("OP18-111"), "43ac6568");
    assert.equal(cardImageUrl("OP18-111"), `${PUBLIC_BASE}/OP18-111.png?h=43ac6568`);
    assert.equal(cardOgImage("OP18-111")?.url, `${PUBLIC_BASE}/OP18-111.png?h=43ac6568`);
    assert.equal(cardImageHash("EB05-008"), "5fd1581b");
    assert.equal(cardImageUrl("EB05-008"), `${PUBLIC_BASE}/EB05-008.png?h=5fd1581b`);
    assert.equal(cardOgImage("EB05-008")?.url, `${PUBLIC_BASE}/EB05-008.png?h=5fd1581b`);
    assert.equal(cardImageHash("EB05-040"), "d88f4308");
    assert.equal(cardImageUrl("EB05-040"), `${PUBLIC_BASE}/EB05-040.png?h=d88f4308`);
    assert.equal(cardOgImage("EB05-040")?.url, `${PUBLIC_BASE}/EB05-040.png?h=d88f4308`);
    assert.equal(cardImageHash("EB05-059"), "29764ed8");
    assert.equal(cardImageUrl("EB05-059"), `${PUBLIC_BASE}/EB05-059.png?h=29764ed8`);
    assert.equal(cardOgImage("EB05-059")?.url, `${PUBLIC_BASE}/EB05-059.png?h=29764ed8`);
    assert.equal(cardImageHash("OP18-076"), "f4749b71");
    assert.equal(cardImageUrl("OP18-076"), `${PUBLIC_BASE}/OP18-076.png?h=f4749b71`);
    assert.equal(cardOgImage("OP18-076")?.url, `${PUBLIC_BASE}/OP18-076.png?h=f4749b71`);
    assert.equal(cardImageHash("OP18-089"), "877a852c");
    assert.equal(cardImageUrl("OP18-089"), `${PUBLIC_BASE}/OP18-089.png?h=877a852c`);
    assert.equal(cardOgImage("OP18-089")?.url, `${PUBLIC_BASE}/OP18-089.png?h=877a852c`);
    assert.equal(cardImageHash("P-160"), "aee899d7");
    assert.equal(cardImageUrl("P-160"), `${PUBLIC_BASE}/P-160.png?h=aee899d7`);
    assert.equal(cardOgImage("P-160")?.url, `${PUBLIC_BASE}/P-160.png?h=aee899d7`);
    assert.equal(cardImageHash("OP18-106"), "d1808e60");
    assert.equal(cardImageUrl("OP18-106"), `${PUBLIC_BASE}/OP18-106.png?h=d1808e60`);
    assert.equal(cardOgImage("OP18-106")?.url, `${PUBLIC_BASE}/OP18-106.png?h=d1808e60`);
    assert.equal(cardImageHash("EB05-049"), "16be5f3f");
    assert.equal(cardImageUrl("EB05-049"), `${PUBLIC_BASE}/EB05-049.png?h=16be5f3f`);
    assert.equal(cardOgImage("EB05-049")?.url, `${PUBLIC_BASE}/EB05-049.png?h=16be5f3f`);
  });

  it("returns no URL and no og image when the manifest has no file", () => {
    for (const id of ["OP18-021-P1", "OP16-098-P2"]) {
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
