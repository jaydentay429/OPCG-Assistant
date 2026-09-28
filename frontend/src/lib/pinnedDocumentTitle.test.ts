import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { homeDocumentTitle } from "./pinnedDocumentTitle.ts";

describe("home document title", () => {
  it("matches the server Traditional title and localizes the other languages", () => {
    assert.equal(
      homeDocumentTitle("zh-Hant"),
      "OPCG 卡牌助手 (optcgassistant) | OPCG Assistant 卡牌搜索・構築・賽事卡組",
    );
    assert.equal(
      homeDocumentTitle("zh-Hans"),
      "OPCG 卡牌助手 (optcgassistant) | OPCG Assistant 卡牌搜索・构筑・赛事卡组",
    );
    assert.equal(
      homeDocumentTitle("en"),
      "OPCG Card Assistant (optcgassistant) | OPCG Assistant Card Search, Deck Building, Tournament Decks",
    );
  });
});
