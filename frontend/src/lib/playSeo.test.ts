import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { describe, it } from "node:test";
import { playPageMetadata } from "./playSeo.ts";

const FRONTEND_ROOT = path.resolve(import.meta.dirname, "../..");

describe("play page metadata", () => {
  it("is noindex, follow on every play path", () => {
    for (const route of ["/play", "/play/rank", "/play/history", "/play/history/abc", "/play/spectate"]) {
      const meta = playPageMetadata({ title: "對戰", description: "練習", path: route });
      const robots = meta.robots as { index: boolean; follow: boolean; googleBot: { index: boolean; follow: boolean } };
      assert.equal(robots.index, false, route);
      assert.equal(robots.follow, true, route);
      assert.equal(robots.googleBot.index, false, route);
      assert.equal(robots.googleBot.follow, true, route);
      assert.equal(meta.alternates && "canonical" in meta.alternates ? meta.alternates.canonical : "", route);
    }
  });
});

describe("play stays out of the sitemap and llms.txt", () => {
  it("does not list /play in the sitemap source", () => {
    const source = fs.readFileSync(path.join(FRONTEND_ROOT, "src/app/sitemap.ts"), "utf8");
    assert.equal(source.includes('"/play"'), false);
    assert.equal(source.includes("'/play'"), false);
    assert.equal(source.includes("`/play"), false);
    assert.equal(source.includes("/play/"), false);
  });

  it("does not list /play in llms.txt", () => {
    const source = fs.readFileSync(path.join(FRONTEND_ROOT, "public/llms.txt"), "utf8");
    assert.equal(source.toLowerCase().includes("/play"), false);
  });
});

describe("robots.txt", () => {
  it("still disallows history and spectate and does not disallow /play itself", () => {
    const source = fs.readFileSync(path.join(FRONTEND_ROOT, "public/robots.txt"), "utf8");
    assert.match(source, /^Disallow: \/play\/history$/m);
    assert.match(source, /^Disallow: \/play\/spectate$/m);
    assert.equal(/^Disallow:\s*\/play\s*$/m.test(source), false);
  });
});

describe("play entry links", () => {
  it("are ordinary links without nofollow", () => {
    const files = [
      "src/components/BottomNav.tsx",
      "src/components/CoverLanding.tsx",
      "src/components/FooterNote.tsx",
      "src/components/HomeIndex.tsx",
      "src/components/SeoIntro.tsx",
    ];
    for (const rel of files) {
      const text = fs.readFileSync(path.join(FRONTEND_ROOT, rel), "utf8");
      assert.match(text, /\/play/, rel);
      assert.equal(text.includes("nofollow"), false, rel);
    }
  });
});
