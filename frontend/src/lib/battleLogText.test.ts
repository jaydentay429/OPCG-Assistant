import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { effectLogKey, humanizeBattleUnit, humanizeEffectSummary, isRawInstanceId } from "./battleLogText.ts";

const t = (key: string) =>
  ({
    "play.zone_leader": "領袖",
    "play.log.card_unnamed": "角色卡",
    "play.log.op_skip_untap": "下一個重整階段無法活動",
    "play.log.op_generic": "已執行效果",
  })[key] || key;

describe("battle log text", () => {
  it("never surfaces instance ids", () => {
    assert.equal(isRawInstanceId("ch_28129064"), true);
    assert.equal(isRawInstanceId("OP18-010"), false);
    assert.equal(humanizeBattleUnit("ch_28129064", {}, "zh-Hant", t), "角色卡");
    assert.equal(humanizeBattleUnit("leader", {}, "zh-Hant", t), "領袖");
    assert.equal(
      humanizeBattleUnit("OP18-010", { "OP18-010": { name: "喬巴", name_en: "Chopper" } }, "zh-Hant", t),
      "喬巴",
    );
  });

  it("maps raw ops and keeps the Chinese half of bilingual prompts", () => {
    assert.equal(humanizeEffectSummary("skip_untap", "zh-Hant", t), "下一個重整階段無法活動");
    assert.equal(humanizeEffectSummary("cannot_attack:leader", "zh-Hant", t), "已執行效果");
    assert.equal(
      humanizeEffectSummary("Trigger: draw 2, trash 1 hand", "zh-Hant", t),
      "",
    );
    assert.equal(
      humanizeEffectSummary("Choose a card to KO / 選擇要擊破的卡", "zh-Hant", t),
      "選擇要擊破的卡",
    );
    assert.equal(
      humanizeEffectSummary("Choose a card to KO / 選擇要擊破的卡", "en", t),
      "Choose a card to KO",
    );
  });

  it("drops unsubstituted effect ids from the log template", () => {
    assert.equal(effectLogKey("play.log.effect_applied", false, "下一個重整階段無法活動"), "play.log.effect_applied_summary");
    assert.equal(effectLogKey("play.log.effect_applied", true, ""), "play.log.effect_applied_bare");
    assert.equal(effectLogKey("play.log.attack", true, ""), "play.log.attack");
  });
});
