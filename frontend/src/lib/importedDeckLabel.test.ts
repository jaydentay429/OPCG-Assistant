import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { importedDeckOptionLabel } from "./importedDeckLabel.ts";

describe("imported deck dropdown label", () => {
  it("translates the Imported sentinel and keeps a pasted name", () => {
    const t = (key: string) => (key === "play.imported_ok" ? "已匯入" : key);
    assert.equal(importedDeckOptionLabel("Imported", "OP12-020-P1", t), "已匯入 · OP12-020 · 50/50");
    assert.equal(importedDeckOptionLabel("", "OP12-020", t), "已匯入 · OP12-020 · 50/50");
    assert.equal(importedDeckOptionLabel("绿鹰眼", "OP12-020", t), "绿鹰眼 · OP12-020 · 50/50");
  });
});
