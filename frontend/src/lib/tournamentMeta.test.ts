import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  compareMetaCategoryKeys,
  formatMetaLabel,
  latestTournamentMetaKeys,
  metaCategoryKey,
  metaCategoryRank,
  tournamentDocumentTitle,
  tournamentMetaKeywords,
  tournamentPageDescription,
  tournamentSeoIntro,
  tournamentSetsFallback,
} from "./tournamentMeta.ts";

describe("metaCategoryKey", () => {
  it("parses JP and EN slugs into short labels", () => {
    assert.equal(
      metaCategoryKey("japan-eb05op18-deck-list-heroines-and-the-dominance-of-god"),
      "EB05+OP18",
    );
    assert.equal(metaCategoryKey("japan-op17-deck-list-the-worlds-strongest-warriors"), "OP17");
    assert.equal(metaCategoryKey("english-op16-deck-list-the-time-of-battle"), "OP16");
    assert.equal(metaCategoryKey("english-op15-eb04-deck-list"), "OP15+EB04");
    assert.equal(metaCategoryKey("jp-format-op-06-twin-champions-decks"), "OP06");
  });
});

describe("metaCategoryRank", () => {
  it("ranks combo keys by the highest set number", () => {
    assert.deepEqual(metaCategoryRank("EB05+OP18").slice(0, 2), [18, 4]);
    assert.deepEqual(metaCategoryRank("OP17").slice(0, 2), [17, 4]);
    assert.ok(compareMetaCategoryKeys("EB05+OP18", "OP17") < 0);
    assert.equal(metaCategoryRank("OP18")[0], metaCategoryRank("EB05+OP18")[0]);
  });
});

describe("latestTournamentMetaKeys", () => {
  const formats = {
    jp: {
      metas: [
        {
          slug: "japan-eb05op18-deck-list",
          title: "Japan: EB05+OP18 Deck List",
          modified: "2026-11-13T03:22:55",
        },
        {
          slug: "japan-op17-deck-list",
          title: "Japan: OP17 Deck List",
          modified: "2026-10-02T03:55:40",
        },
        {
          slug: "japan-op16-deck-list",
          title: "Japan: OP16 Deck List",
          modified: "2026-08-17T03:21:06",
        },
      ],
    },
    en: {
      metas: [
        {
          slug: "english-eb05op18-deck-list",
          title: "English: EB05+OP18 Deck List",
          modified: "2026-10-20T04:21:26",
        },
        {
          slug: "english-op17-deck-list",
          title: "English: OP17 Deck List",
          modified: "2026-09-28T02:45:31",
        },
      ],
    },
  };

  it("returns the newest unique environments, JP/EN merged", () => {
    assert.deepEqual(latestTournamentMetaKeys(formats), ["EB05+OP18", "OP17"]);
  });

  it("falls back to set number when dates are missing", () => {
    assert.deepEqual(
      latestTournamentMetaKeys({
        jp: {
          metas: [
            { slug: "japan-op16-deck-list" },
            { slug: "japan-eb05op18-deck-list" },
            { slug: "japan-op17-deck-list" },
          ],
        },
      }),
      ["EB05+OP18", "OP17"],
    );
  });

  it("returns an empty list when there is no data", () => {
    assert.deepEqual(latestTournamentMetaKeys(undefined), []);
    assert.deepEqual(latestTournamentMetaKeys({ jp: { metas: [] }, en: { metas: [] } }), []);
  });
});

describe("tournament copy", () => {
  it("builds titles and descriptions for all three languages", () => {
    const keys = ["EB05+OP18", "OP17"];
    const phrase = formatMetaLabel(keys);
    assert.equal(phrase, "EB05+OP18 / OP17");
    assert.equal(
      tournamentDocumentTitle("zh-Hant", keys),
      "EB05+OP18 / OP17 Deck List 賽事卡組 | OPCG Assistant 比賽卡組瀏覽",
    );
    assert.equal(
      tournamentDocumentTitle("zh-Hans", keys),
      "EB05+OP18 / OP17 Deck List 赛事卡组 | OPCG Assistant 比赛卡组浏览",
    );
    assert.equal(
      tournamentDocumentTitle("en", keys),
      "EB05+OP18 / OP17 Tournament Deck Lists | OPCG Assistant",
    );
    assert.match(tournamentPageDescription("zh-Hant", keys), /EB05\+OP18 \/ OP17/);
    assert.match(tournamentPageDescription("zh-Hans", keys), /EB05\+OP18 \/ OP17/);
    assert.match(tournamentPageDescription("en", keys), /EB05\+OP18 \/ OP17/);
    assert.match(tournamentSeoIntro(keys), /EB05\+OP18 \/ OP17/);
    assert.ok(tournamentMetaKeywords(keys).includes("EB05+OP18 deck list"));
    assert.ok(tournamentMetaKeywords(keys).includes("OP18 deck list"));
    assert.ok(tournamentMetaKeywords(keys).includes("EB05 deck list"));
    assert.ok(!tournamentMetaKeywords(keys).includes("EB5 deck list"));
    assert.ok(!tournamentDocumentTitle("zh-Hant", []).includes("OP17"));
    assert.equal(tournamentSetsFallback("zh-Hant"), "最新環境");
    assert.equal(tournamentSetsFallback("zh-Hans"), "最新环境");
    assert.equal(tournamentSetsFallback("en"), "the latest meta");
  });
});
