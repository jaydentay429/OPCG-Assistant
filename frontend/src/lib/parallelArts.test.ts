import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import {
  cardCanonicalUrl,
  cardMetaDescription,
  isParallelArtId,
  parallelArtIdsAmong,
  sitemapCardIds,
} from "./parallelArts.ts";

describe("isParallelArtId", () => {
  it("treats -P plus digits as alternate art, using the existing base-id rules", () => {
    assert.equal(isParallelArtId("OP05-093-P1"), true);
    assert.equal(isParallelArtId("op05-093-p4"), true);
    assert.equal(isParallelArtId("ST18-005-P2"), true);
    assert.equal(isParallelArtId("P-084-P1"), true);
    assert.equal(isParallelArtId("EB01-001-P3"), true);
  });

  it("does not treat the base card, a reprint, a promo base, or a DON id as alternate art", () => {
    assert.equal(isParallelArtId("OP05-093"), false);
    assert.equal(isParallelArtId("OP05-119-R1"), false);
    assert.equal(isParallelArtId("ST01-002-R1"), false);
    assert.equal(isParallelArtId("P-084"), false);
    assert.equal(isParallelArtId("P-001"), false);
    assert.equal(isParallelArtId("DON17-10163"), false);
    assert.equal(isParallelArtId("OP05-093-P"), false);
    assert.equal(isParallelArtId(""), false);
  });
});

describe("cardCanonicalUrl", () => {
  it("points alternate art at the base card on the hardcoded public origin", () => {
    assert.equal(cardCanonicalUrl("OP05-093-P1"), "https://optcgassistant.com/cards/OP05-093");
    assert.equal(cardCanonicalUrl("OP05-093-P4"), "https://optcgassistant.com/cards/OP05-093");
    assert.equal(cardCanonicalUrl("op05-093-p2"), "https://optcgassistant.com/cards/OP05-093");
    assert.equal(cardCanonicalUrl("P-084-P1"), "https://optcgassistant.com/cards/P-084");
    assert.equal(cardCanonicalUrl("ST18-005-P2"), "https://optcgassistant.com/cards/ST18-005");
  });

  it("keeps a base card and a reprint self-canonical", () => {
    assert.equal(cardCanonicalUrl("OP05-093"), "https://optcgassistant.com/cards/OP05-093");
    assert.equal(cardCanonicalUrl("EB01-002"), "https://optcgassistant.com/cards/EB01-002");
    assert.equal(cardCanonicalUrl("OP05-119-R1"), "https://optcgassistant.com/cards/OP05-119-R1");
    assert.equal(cardCanonicalUrl("P-084"), "https://optcgassistant.com/cards/P-084");
  });

  it("never uses a request host", () => {
    for (const id of ["OP05-093-P1", "OP05-093", "OP05-119-R1", "P-084-P1"]) {
      const url = cardCanonicalUrl(id);
      assert.equal(url.includes("localhost"), false, url);
      assert.equal(url.includes("127.0.0.1"), false, url);
      assert.ok(url.startsWith("https://optcgassistant.com/cards/"), url);
    }
  });
});

describe("sitemapCardIds", () => {
  it("drops -P urls and keeps base cards, reprints, promos, and DON ids", () => {
    assert.deepEqual(
      sitemapCardIds([
        "OP05-093",
        "OP05-093-P1",
        "OP05-093-P2",
        "OP05-119-R1",
        "P-084",
        "P-084-P1",
        "DON17-10163",
        "",
      ]),
      ["OP05-093", "OP05-119-R1", "P-084", "DON17-10163"],
    );
  });

  it("removes every bundled alternate-art id and no other card id", () => {
    const ids = JSON.parse(
      readFileSync(new URL("../generated/card-ids.json", import.meta.url), "utf8"),
    ) as string[];
    const kept = sitemapCardIds(ids);
    const removed = ids.length - kept.length;
    assert.equal(removed, ids.filter((id) => isParallelArtId(id)).length);
    assert.ok(kept.every((id) => !isParallelArtId(id)));
    assert.equal(kept.includes("OP05-093"), true);
    assert.equal(kept.includes("OP05-093-P1"), false);
    assert.equal(kept.includes("EB01-002"), true);
    assert.ok(ids.includes("OP05-119-R1"));
    assert.equal(kept.includes("OP05-119-R1"), true);
    assert.equal(removed > 0, true);
  });
});

describe("parallelArtIdsAmong", () => {
  const catalog = [
    "OP05-093",
    "OP05-093-P1",
    "OP05-093-P2",
    "OP05-093-P4",
    "OP05-093-P3",
    "OP05-093-R1",
    "OP05-094-P1",
    "EB01-002",
  ];

  it("lists every -P printing of the base card in numeric order", () => {
    assert.deepEqual(parallelArtIdsAmong("OP05-093", catalog), [
      "OP05-093-P1",
      "OP05-093-P2",
      "OP05-093-P3",
      "OP05-093-P4",
    ]);
  });

  it("omits the current alternate-art page and reprint ids", () => {
    assert.deepEqual(parallelArtIdsAmong("OP05-093-P1", catalog), [
      "OP05-093-P2",
      "OP05-093-P3",
      "OP05-093-P4",
    ]);
    assert.deepEqual(parallelArtIdsAmong("EB01-002", catalog), []);
  });
});

describe("cardMetaDescription", () => {
  it("matches the full description when every field is present", () => {
    assert.equal(
      cardMetaDescription({
        name: "羅布・路基",
        id: "OP05-093",
        series: "OP05",
        rarity: "SR",
        cardType: "Character",
        effect: "【登場時】抽 1 張。",
      }),
      "羅布・路基（OP05-093）是《ONE PIECE 卡牌對戰》卡牌，系列 OP05，稀有度 SR，類型 Character。效果：【登場時】抽 1 張。",
    );
  });

  it("drops empty series, rarity, and type placeholders", () => {
    const text = cardMetaDescription({
      name: "阿娜",
      id: "OP05-062",
      series: "-",
      rarity: "—",
      cardType: "－",
      effect: "-",
    });
    assert.equal(text.includes("系列 -"), false);
    assert.equal(text.includes("稀有度"), false);
    assert.equal(text.includes("類型"), false);
    assert.equal(text.includes("效果"), false);
    assert.equal(text, "阿娜（OP05-062）是《ONE PIECE 卡牌對戰》卡牌。");
  });
});
