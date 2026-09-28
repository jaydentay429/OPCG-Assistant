#!/usr/bin/env node
/**
 * Fail the build when the card-image manifest is missing, unreadable, empty,
 * or below the floor. The floor is 95% of the snapshot committed with this
 * change (see CARD_IMAGE_MANIFEST_MIN_COUNT). A later sync may grow the file;
 * it must not ship a drop of more than 5%.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

/** 95% of the committed snapshot (5274 entries → 5010). Update when that count changes. */
export const CARD_IMAGE_MANIFEST_MIN_COUNT = 5010;

const frontendRoot = join(dirname(fileURLToPath(import.meta.url)), "..");

function main() {
  const file =
    process.env.CARD_IMAGE_MANIFEST || join(frontendRoot, "src/generated/card-image-manifest.json");
  const minRaw = process.env.CARD_IMAGE_MANIFEST_MIN_COUNT;
  const minCount =
    minRaw != null && minRaw !== "" ? Number(minRaw) : CARD_IMAGE_MANIFEST_MIN_COUNT;
  if (!Number.isFinite(minCount) || minCount < 0) {
    console.error(`[card-image-manifest] invalid floor: ${minRaw}`);
    process.exit(1);
  }

  let text;
  try {
    text = readFileSync(file, "utf8");
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    console.error(`[card-image-manifest] missing ${file}: ${message}`);
    process.exit(1);
  }

  let data;
  try {
    data = JSON.parse(text);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    console.error(`[card-image-manifest] unreadable: ${message}`);
    process.exit(1);
  }
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    console.error("[card-image-manifest] manifest must be a JSON object");
    process.exit(1);
  }
  const count = Object.keys(data).length;
  if (count === 0) {
    console.error("[card-image-manifest] manifest is empty");
    process.exit(1);
  }
  if (count < minCount) {
    console.error(
      `[card-image-manifest] manifest has ${count} entries, floor is ${minCount}`,
    );
    process.exit(1);
  }
  console.log(`[card-image-manifest] ${count} entries (floor ${minCount})`);
}

main();
