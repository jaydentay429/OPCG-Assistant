import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { cardImagePacksUrl, cardImageProxyUrl, cardImageUrl } from "./api";
import {
  cardImagePlaceholderLabel,
  exportCardImagePlan,
} from "./exportCardImage";

describe("exportCardImagePlan", () => {
  it("tries the page CDN url before the API packs and proxy urls", () => {
    for (const id of ["EB05-016", "EB05-016-P1", "OP18-016", "OP13-001"]) {
      const plan = exportCardImagePlan(id);
      const cdn = cardImageUrl(id);
      assert.ok(cdn.startsWith("https://img.optcgassistant.com/"));
      assert.match(cdn, new RegExp(`/${id}\\.png\\?h=[0-9a-f]{8}$`));
      assert.equal(plan.cdn, cdn);
      assert.deepEqual(plan.api, [cardImagePacksUrl(id), cardImageProxyUrl(id)]);
      assert.equal(plan.api[0].includes("/packs/"), true);
      assert.equal(plan.api[1].includes("/images/card/"), true);
      assert.equal(plan.cdn.includes("/packs/"), false);
    }
  });

  it("skips the API when cardImageUrl is empty", () => {
    const plan = exportCardImagePlan("OP18-112");
    assert.equal(cardImageUrl("OP18-112"), "");
    assert.equal(plan.cdn, "");
    assert.deepEqual(plan.api, []);
  });

  it("uses the same placeholder captions as the card page", () => {
    assert.equal(cardImagePlaceholderLabel("zh-Hant"), "暫無圖片");
    assert.equal(cardImagePlaceholderLabel("zh-Hans"), "暂无图片");
    assert.equal(cardImagePlaceholderLabel("en"), "No image");
  });
});
