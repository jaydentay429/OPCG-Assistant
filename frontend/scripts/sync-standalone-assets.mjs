#!/usr/bin/env node
/**
 * After `next build`, copy static + public into `.next/standalone`
 * so `node .next/standalone/server.js` can serve /_next/static chunks.
 */
import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { join } from "node:path";

const root = process.cwd();
const standalone = join(root, ".next", "standalone");
const staticSrc = join(root, ".next", "static");
const publicSrc = join(root, "public");

if (!existsSync(standalone)) {
  console.warn("[sync-standalone-assets] no .next/standalone — skip");
  process.exit(0);
}
if (!existsSync(staticSrc)) {
  console.error("[sync-standalone-assets] missing .next/static");
  process.exit(1);
}

mkdirSync(join(standalone, ".next"), { recursive: true });
const staticDest = join(standalone, ".next", "static");
rmSync(staticDest, { recursive: true, force: true });
cpSync(staticSrc, staticDest, { recursive: true });

if (existsSync(publicSrc)) {
  const publicDest = join(standalone, "public");
  rmSync(publicDest, { recursive: true, force: true });
  cpSync(publicSrc, publicDest, { recursive: true });
}

console.log("[sync-standalone-assets] copied static (+ public) into standalone");
