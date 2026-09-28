import assert from "node:assert/strict";
import { describe, it } from "node:test";
import * as OpenCC from "opencc-js";
import { HANS_PHRASE_FIXES } from "../locales/hansPhraseFixes.generated.ts";
import { localizeCardName, toSimplifiedText } from "./cardLocale.ts";
import { expandQueryNorms } from "./cardSearchMatch.ts";
import { ensureHansConverter, ensureHantConverter, openccLoadState } from "./openccLazy.ts";

function applyHansPhraseFixes(text: string): string {
  let out = text;
  for (const [from, to] of HANS_PHRASE_FIXES) {
    if (!from || from === to) continue;
    out = out.split(from).join(to);
  }
  return out;
}

describe("lazy opencc dictionaries", () => {
  it("keeps the default path off the dictionaries and matches OpenCC after load", async () => {
    const fullHans = OpenCC.Converter({ from: "tw", to: "cn" });
    const fullHant = OpenCC.Converter({ from: "cn", to: "tw" });

    assert.deepEqual(openccLoadState(), { hans: "idle", hant: "idle" });
    assert.equal(localizeCardName("蒙其・D・魯夫", "Monkey.D.Luffy", "zh-Hant"), "魯夫");
    assert.equal(localizeCardName("蒙其・D・魯夫", "Monkey.D.Luffy", "en"), "Monkey.D.Luffy");
    assert.equal(localizeCardName("海道", "Kaido", "zh-Hans"), "凯多");
    assert.equal(toSimplifiedText(""), "");
    assert.equal(toSimplifiedText(null), "");
    // No browser: show the original and do not start a download.
    assert.equal(toSimplifiedText("測試"), "測試");
    const before = expandQueryNorms("路飞");
    assert.ok(before.includes("路飞"));
    assert.ok(before.includes("魯夫"));
    assert.ok(before.includes("鲁夫"));
    assert.equal(before.includes("路飛"), false);
    expandQueryNorms("OP01-001");
    assert.deepEqual(openccLoadState(), { hans: "idle", hant: "idle" });

    Object.assign(globalThis, { window: {} });

    expandQueryNorms("ST01-001");
    assert.deepEqual(openccLoadState(), { hans: "idle", hant: "idle" });

    assert.equal(toSimplifiedText("測試"), "測試");
    assert.equal(openccLoadState().hans, "loading");
    assert.equal(await ensureHansConverter(), await ensureHansConverter());
    assert.equal(openccLoadState().hans, "ready");
    assert.equal(openccLoadState().hant, "idle");

    for (const sample of ["測試", "國", "臺灣", "一針見血", "蒙其・D・魯夫", "海道"]) {
      assert.equal(toSimplifiedText(sample), applyHansPhraseFixes(fullHans(sample)));
    }
    assert.equal(toSimplifiedText("蒙其・D・魯夫"), "蒙奇・D・路飞");

    const pending = expandQueryNorms("路飞");
    assert.equal(pending.includes("路飛"), false);
    assert.equal(openccLoadState().hant, "loading");
    await ensureHantConverter();
    assert.equal(openccLoadState().hant, "ready");

    const after = expandQueryNorms("路飞");
    assert.ok(after.includes("路飞"));
    assert.ok(after.includes("路飛"));
    assert.ok(after.includes("魯夫"));
    assert.equal(fullHant("路飞"), "路飛");
    const software = expandQueryNorms("软件");
    assert.ok(software.includes(fullHant("软件")));

    for (const sample of ["软件", "网络", "鼠标", "国", "台湾"]) {
      assert.equal(
        expandQueryNorms(sample).includes(fullHant(sample)),
        true,
        sample,
      );
    }
  });
});
