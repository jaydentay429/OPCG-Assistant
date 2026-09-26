import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { resolvePacksCdnBase } from "./api.ts";
import {
  cardDocumentTitle,
  cardHeadingText,
  cardIdFromPathname,
  isSameCardFamily,
  leaderLifeValue,
  marketPriceToResponse,
  printedCostOrLife,
  shouldDeferVariantClick,
  shownCardId,
  variantMainAlt,
  variantThumbAlt,
} from "./cardPageView.ts";

describe("printed cost versus life", () => {
  it("shows life for a leader even though the API copies that number into cost", () => {
    const stat = printedCostOrLife({
      card_type: "Leader",
      card_type_en: "Leader",
      cost: 5,
      life: 5,
    });
    assert.deepEqual(stat, { kind: "life", value: 5 });
    assert.equal(leaderLifeValue({ life: null, cost: 4 }), 4);
  });

  it("keeps cost for a character whose life field duplicates cost", () => {
    assert.deepEqual(
      printedCostOrLife({
        card_type: "Character",
        card_type_en: "Character",
        cost: 4,
        life: 4,
      }),
      { kind: "cost", value: 4 },
    );
    assert.deepEqual(
      printedCostOrLife({ card_type: "Character", cost: 3, life: null }),
      { kind: "cost", value: 3 },
    );
  });
});

describe("alternate-art labels", () => {
  it("writes thumbnail alt as 卡名（卡號）異畫 and keeps that printing on the main image", () => {
    assert.equal(variantThumbAlt("路基", "OP05-093-P2"), "路基（OP05-093-P2）異畫");
    assert.equal(variantMainAlt("路基", "op05-093-p2"), "路基（OP05-093-P2）異畫");
    assert.equal(variantThumbAlt("路基", "OP05-093"), "路基（OP05-093）");
    assert.equal(variantMainAlt("戈爾德伯格", "OP18-086"), "戈爾德伯格");
  });

  it("adds one alternate-art suffix from the id, in the page language", () => {
    assert.equal(
      cardDocumentTitle("騙人布", "ST01-002-P2"),
      "騙人布(異圖卡)（ST01-002）| OPCG 卡牌資料",
    );
    assert.equal(
      cardDocumentTitle("羅布・路基(異圖卡)", "OP05-093-P1"),
      "羅布・路基(異圖卡)（OP05-093）| OPCG 卡牌資料",
    );
    assert.equal(
      cardDocumentTitle("骗人布", "ST01-002-P2", "zh-Hans"),
      "骗人布(异图卡)（ST01-002）| OPCG 卡牌資料",
    );
    assert.equal(
      cardDocumentTitle("Usopp", "ST01-002-P2", "en"),
      "Usopp (Parallel)（ST01-002）| OPCG 卡牌資料",
    );
    assert.equal(
      cardDocumentTitle("Rob Lucci (Parallel)", "OP05-093-P1", "en"),
      "Rob Lucci (Parallel)（OP05-093）| OPCG 卡牌資料",
    );
    assert.equal(
      cardDocumentTitle("羅布・路基", "OP05-093"),
      "羅布・路基（OP05-093）| OPCG 卡牌資料",
    );
    assert.equal(
      cardDocumentTitle("騙人布", "ST01-002-R1"),
      "騙人布（ST01-002）| OPCG 卡牌資料",
    );
  });

  it("writes the same suffix into the H1 and keeps a reprint thumb distinct", () => {
    assert.equal(
      cardHeadingText("騙人布", "Usopp", "ST01-002-P2"),
      "騙人布(異圖卡) / Usopp (Parallel) ST01-002",
    );
    assert.equal(
      cardHeadingText("羅布・路基(異圖卡)", "Rob Lucci (Parallel)", "OP05-093-P1"),
      "羅布・路基(異圖卡) / Rob Lucci (Parallel) OP05-093",
    );
    assert.equal(
      cardHeadingText("骗人布", "Usopp", "ST01-002-P2", "zh-Hans"),
      "骗人布(异图卡) / Usopp (Parallel) ST01-002",
    );
    assert.equal(
      cardHeadingText("騙人布", "Usopp", "ST01-002-P2", "en"),
      "Usopp (Parallel) / 騙人布(異圖卡) ST01-002",
    );
    assert.equal(cardHeadingText("騙人布", "Usopp", "ST01-002"), "騙人布 / Usopp ST01-002");
    const reprint = variantThumbAlt("騙人布", "ST01-002-R1");
    const base = variantThumbAlt("騙人布", "ST01-002");
    assert.notEqual(reprint, base);
    assert.match(reprint, /R1/);
    assert.equal(reprint, "騙人布（ST01-002-R1）");
  });

  it("selects the query variant before the path id", () => {
    assert.equal(shownCardId("OP05-093", "", "OP05-093-P1"), "OP05-093-P1");
    assert.equal(shownCardId("OP05-093", "OP05-093-P2", ""), "OP05-093-P2");
    assert.equal(shownCardId("OP05-093-P1"), "OP05-093-P1");
    assert.equal(shownCardId("OP05-093", "ST01-002-P1"), "OP05-093");
  });
});

describe("variant history clicks", () => {
  it("lets modifier and middle clicks open a new tab", () => {
    assert.equal(shouldDeferVariantClick({ button: 0 }), false);
    assert.equal(shouldDeferVariantClick({}), false);
    assert.equal(shouldDeferVariantClick({ button: 1 }), true);
    assert.equal(shouldDeferVariantClick({ button: 0, metaKey: true }), true);
    assert.equal(shouldDeferVariantClick({ button: 0, ctrlKey: true }), true);
    assert.equal(shouldDeferVariantClick({ button: 0, shiftKey: true }), true);
  });

  it("reads a card id back out of the path for popstate", () => {
    assert.equal(cardIdFromPathname("/cards/OP05-093-P2"), "OP05-093-P2");
    assert.equal(cardIdFromPathname("/cards/OP05-093"), "OP05-093");
    assert.equal(isSameCardFamily("OP05-093-P3", "OP05-093"), true);
    assert.equal(isSameCardFamily("OP05-093-P2", "ST01-001"), false);
  });
});

describe("market price seed", () => {
  it("turns the card payload into a price response and keeps a missing history empty", () => {
    const price = marketPriceToResponse("OP05-093-P2", {
      source: "yuyu-tei",
      currency: "JPY",
      current_price: 5980,
      history: [{ ts: "2026-08-28T07:22:53+00:00", price: 5980 }],
    });
    assert.equal(price?.card_id, "OP05-093-P2");
    assert.equal(price?.current_price, 5980);
    assert.equal(price?.history.length, 1);
    const empty = marketPriceToResponse("OP18-086", {
      source: "yuyu-tei",
      currency: "JPY",
      current_price: null,
    });
    assert.equal(empty?.current_price, null);
    assert.deepEqual(empty?.history, []);
    assert.equal(marketPriceToResponse("OP18-086", null), null);
  });
});

describe("packs CDN base", () => {
  it("defaults to the public image host when the site URL is unset", () => {
    assert.equal(
      resolvePacksCdnBase({ packsCdnUrl: "", siteUrl: "" }),
      "https://img.optcgassistant.com",
    );
    assert.equal(
      resolvePacksCdnBase({ siteUrl: "https://optcgassistant.com" }),
      "https://img.optcgassistant.com",
    );
    assert.equal(
      resolvePacksCdnBase({ packsCdnUrl: "https://cdn.example.test/" }),
      "https://cdn.example.test",
    );
    assert.equal(
      resolvePacksCdnBase({ siteUrl: "https://preview.example.test", hostname: "localhost" }),
      "",
    );
  });
});
