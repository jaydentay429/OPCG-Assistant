import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { filterBinderLibrary, type BinderLibraryMeta } from "./binderLibraryFilter";

/** QA account: ST01-001, ST01-002, ST01-003, one copy each. */
const FIXTURE = [
  ["ST01-001", 1],
  ["ST01-002", 1],
  ["ST01-003", 1],
] as const;

const NO_META: Record<string, BinderLibraryMeta> = {};

function ids(entries: readonly (readonly [string, ...unknown[]])[]): string[] {
  return entries.map(([id]) => id);
}

function rejectNameLookup(): never {
  throw new Error("card-number search must not wait for name metadata");
}

describe("filterBinderLibrary", () => {
  it("filters a full card number even when deck-stats metadata never arrives", () => {
    const matched = filterBinderLibrary(FIXTURE, "ST01-003", NO_META, rejectNameLookup);
    assert.deepEqual(ids(matched), ["ST01-003"]);
  });

  it("matches partial, case, and separator variants of a card number", () => {
    const queries = ["st01-003", "ST01003", "st01 003", "ST-01-003", "ST01_003", "ST01－003", "ST01–003", "003"];
    for (const query of queries) {
      assert.deepEqual(ids(filterBinderLibrary(FIXTURE, query, NO_META)), ["ST01-003"], query);
    }
    assert.deepEqual(ids(filterBinderLibrary(FIXTURE, "ST01", NO_META)), ["ST01-001", "ST01-002", "ST01-003"]);
    assert.deepEqual(ids(filterBinderLibrary(FIXTURE, "001", NO_META)), ["ST01-001"]);
    assert.deepEqual(ids(filterBinderLibrary(FIXTURE, "OP01-001", NO_META)), []);
  });

  it("matches a displayed base id against a parallel suffix", () => {
    const entries = [["OP01-001-P1", 1]] as const;
    assert.deepEqual(ids(filterBinderLibrary(entries, "op01-001", NO_META)), ["OP01-001-P1"]);
    assert.deepEqual(ids(filterBinderLibrary(entries, "OP01001", NO_META)), ["OP01-001-P1"]);
  });

  it("restores the full list when the search is cleared", () => {
    assert.deepEqual(ids(filterBinderLibrary(FIXTURE, "", NO_META)), ["ST01-001", "ST01-002", "ST01-003"]);
    assert.deepEqual(ids(filterBinderLibrary(FIXTURE, "   ", NO_META)), ["ST01-001", "ST01-002", "ST01-003"]);
  });

  it("keeps name search working once metadata is loaded, and does not flash empty before that", () => {
    const meta: Record<string, BinderLibraryMeta> = {
      "ST01-001": { searchBlob: "蒙其d路飞monkeydluffy" },
      "ST01-002": { searchBlob: "罗罗诺亚索隆roronoazoro" },
      "ST01-003": { searchBlob: "纳美nami" },
    };
    const matchName = (_id: string, blob: string | null | undefined, query: string) =>
      String(blob || "").includes(query.trim().toLowerCase());

    assert.deepEqual(ids(filterBinderLibrary(FIXTURE, "luffy", NO_META, matchName)), [
      "ST01-001",
      "ST01-002",
      "ST01-003",
    ]);
    assert.deepEqual(ids(filterBinderLibrary(FIXTURE, "luffy", meta, matchName)), ["ST01-001"]);
    assert.deepEqual(ids(filterBinderLibrary(FIXTURE, "zoro", meta, matchName)), ["ST01-002"]);
    assert.deepEqual(ids(filterBinderLibrary(FIXTURE, "nami", meta, matchName)), ["ST01-003"]);
    assert.deepEqual(ids(filterBinderLibrary(FIXTURE, "sanji", meta, matchName)), []);
  });

  it("does not treat a card number as a substring of another id", () => {
    const entries = [
      ["OP16-001", 1],
      ["OP16-001-P1", 1],
      ["P-160", 1],
      ["OP18-076", 1],
    ] as const;
    assert.deepEqual(ids(filterBinderLibrary(entries, "P-160", NO_META)), ["P-160"]);
    assert.deepEqual(ids(filterBinderLibrary(entries, "p160", NO_META)), ["P-160"]);
    assert.deepEqual(ids(filterBinderLibrary(entries, "OP18-076", NO_META)), ["OP18-076"]);
    assert.deepEqual(ids(filterBinderLibrary(entries, "op18076", NO_META)), ["OP18-076"]);
    assert.deepEqual(ids(filterBinderLibrary(entries, "OP18", NO_META)), ["OP18-076"]);
  });

  it("does not match card numbers from digits inside a name", () => {
    const entries = [
      ["OP16-003", 1],
      ["ST01-002", 1],
      ["OP18-076", 1],
      ["OP18-078", 1],
    ] as const;
    const meta: Record<string, BinderLibraryMeta> = {
      "OP16-003": { searchBlob: "其他卡" },
      "ST01-002": { searchBlob: "其他" },
      "OP18-076": { searchBlob: "鯊魚潛水3號sharksubmergeno3" },
      "OP18-078": { searchBlob: "迷你梅利2號minimerryno2" },
    };
    const matchName = (_id: string, blob: string | null | undefined, query: string) =>
      String(blob || "").includes(query.replace(/\s+/g, ""));
    assert.deepEqual(ids(filterBinderLibrary(entries, "鯊魚潛水3號", meta, matchName)), ["OP18-076"]);
    assert.deepEqual(ids(filterBinderLibrary(entries, "迷你梅利2號", meta, matchName)), ["OP18-078"]);
    assert.deepEqual(ids(filterBinderLibrary(entries, "路飞", meta, matchName)), []);
  });
});
