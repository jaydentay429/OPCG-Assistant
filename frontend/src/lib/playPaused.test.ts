import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { describe, it } from "node:test";
import { playPausedMetadata, playPausedPath } from "./playPaused.ts";

const FRONTEND_ROOT = path.resolve(import.meta.dirname, "../..");
const SRC_ROOT = path.join(FRONTEND_ROOT, "src");

/** Internal links into the paused battle pages. Disallow lines are not links. */
const PLAY_HREF_RE = /href\s*[:=]\s*["']\/play(?=["'?#/]|$)/g;

function listSourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "play" && dir.endsWith(`${path.sep}components`)) continue;
      out.push(...listSourceFiles(full));
      continue;
    }
    if (!entry.isFile()) continue;
    if (entry.name.endsWith(".test.ts")) continue;
    if (/\.(?:tsx?|jsx?|css|txt|json)$/.test(entry.name)) out.push(full);
  }
  return out;
}

function playHrefHits(text: string): string[] {
  return text.match(PLAY_HREF_RE) ?? [];
}

describe("play paused notice", () => {
  it("builds one path for /play and every nested slug", () => {
    assert.equal(playPausedPath(undefined), "/play");
    assert.equal(playPausedPath([]), "/play");
    assert.equal(playPausedPath(["rank"]), "/play/rank");
    assert.equal(playPausedPath(["room", "xxx"]), "/play/room/xxx");
  });

  it("is noindex, follow, without hreflang, and canonical stays on /play", () => {
    for (const slug of [undefined, ["rank"], ["room", "xxx"]] as const) {
      const meta = playPausedMetadata(slug ? [...slug] : undefined);
      assert.equal(meta.robots.index, false);
      assert.equal(meta.robots.follow, true);
      assert.equal(meta.robots.googleBot.index, false);
      assert.equal(meta.robots.googleBot.follow, true);
      assert.equal("languages" in meta.alternates, false);
      assert.equal(meta.alternates.canonical, `https://optcgassistant.com${playPausedPath(slug ? [...slug] : undefined)}`);
      assert.equal(meta.alternates.canonical.includes("/builder"), false);
      assert.equal(meta.alternates.canonical.includes("localhost"), false);
      assert.equal(meta.openGraph.url, meta.alternates.canonical);
    }
  });
});

describe("sitemap has no battle urls", () => {
  it("does not list /play or /play/*", () => {
    const source = fs.readFileSync(path.join(SRC_ROOT, "app/sitemap.ts"), "utf8");
    assert.deepEqual(playHrefHits(source), []);
    assert.equal(source.includes('"/play"'), false);
    assert.equal(source.includes("'/play'"), false);
    assert.equal(source.includes("`/play"), false);
  });
});

describe("internal /play links", () => {
  it("are gone from routed source (parked battle UI excluded)", () => {
    const hits: string[] = [];
    for (const file of listSourceFiles(SRC_ROOT)) {
      const text = fs.readFileSync(file, "utf8");
      const found = playHrefHits(text);
      if (found.length) hits.push(`${path.relative(FRONTEND_ROOT, file)}: ${found.join(", ")}`);
    }
    assert.deepEqual(hits, []);
  });

  it("are gone from the production build when .next exists", () => {
    const nextDir = path.join(FRONTEND_ROOT, ".next");
    if (!fs.existsSync(path.join(nextDir, "BUILD_ID"))) return;
    const hits: string[] = [];
    const walk = (dir: string) => {
      for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        if (entry.name === "cache" || entry.name === "diagnostics") continue;
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) {
          walk(full);
          continue;
        }
        if (!/\.(?:html|js|json|txt|rsc|css)$/.test(entry.name)) continue;
        const text = fs.readFileSync(full, "utf8");
        const found = playHrefHits(text);
        if (found.length) hits.push(`${path.relative(FRONTEND_ROOT, full)}: ${found.slice(0, 4).join(", ")}`);
      }
    };
    walk(nextDir);
    assert.deepEqual(hits, []);
  });
});
