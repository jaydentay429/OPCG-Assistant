import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { splitEffectTrigger } from "./formatEffect";

const PUDDING_MAIN =
  "【主要】抽1張卡片，且自己原本力量值4000、擁有《BIG MOM海賊團》特徵的角色卡全數，在下一個對手回合結束前，在對戰中不會遭到KO。";
const PUDDING_TRIGGER =
  "【觸發器】抽1張卡片，並使最多1張自己手牌中力量值4000且持有【觸發器】的角色卡登場。";
const PUDDING_TRIGGER_HANS =
  "【触发器】抽1张卡片，并使最多1张自己手牌中力量值4000且持有【触发器】的角色卡登场。";

describe("splitEffectTrigger", () => {
  it("keeps a stored trigger out of the effect body", () => {
    const split = splitEffectTrigger(PUDDING_MAIN, PUDDING_TRIGGER);
    assert.equal(split.body, PUDDING_MAIN);
    assert.equal(split.trigger, PUDDING_TRIGGER);
    assert.equal(split.body.includes("【觸發器】"), false);
  });

  it("splits a simplified 【触发器】 line when the trigger field is empty", () => {
    const effect = `${PUDDING_MAIN}\n${PUDDING_TRIGGER_HANS}`;
    const split = splitEffectTrigger(effect, "");
    assert.equal(split.trigger, PUDDING_TRIGGER_HANS);
    assert.equal(split.body, PUDDING_MAIN);
    assert.equal(split.body.includes("【触发器】"), false);
  });

  it("splits traditional, short simplified, and English trigger lines", () => {
    const cases = [
      ["【主要】抽1張。\n【觸發器】抽1張。", "【主要】抽1張。", "【觸發器】抽1張。"],
      ["【主要】抽1张。\n【触发】抽1张。", "【主要】抽1张。", "【触发】抽1张。"],
      ["[Main] Draw 1.\n[Trigger] Draw 1.", "[Main] Draw 1.", "[Trigger] Draw 1."],
    ] as const;
    for (const [effect, body, trigger] of cases) {
      const split = splitEffectTrigger(effect, "");
      assert.equal(split.body, body);
      assert.equal(split.trigger, trigger);
    }
  });

  it("does not treat a mid-line 持有【触发器】 as the trigger timing", () => {
    const effect = "【主要】使持有【触发器】的角色卡登場。";
    const split = splitEffectTrigger(effect, "");
    assert.equal(split.trigger, "");
    assert.equal(split.body, effect);
  });
});
