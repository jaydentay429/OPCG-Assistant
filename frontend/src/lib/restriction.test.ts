import assert from "node:assert/strict";
import { describe, it } from "node:test";
import * as OpenCC from "opencc-js";
import en from "@/locales/en";
import zhHans from "@/locales/zh-Hans";
import zhHant from "@/locales/zh-Hant";
import {
  RESTRICTION_ENTRIES,
  bannedBadgeText,
  deckRestrictionWarnings,
  restrictionPhrase,
} from "./restriction.ts";

const BANNED = ["OP03-040", "OP06-047", "OP06-086", "OP06-116", "OP14-020", "ST10-001"];
const PAIRS = [
  ["OP07-115", "EB04-058"],
  ["OP11-040", "OP11-067"],
  ["OP11-040", "OP08-069"],
];
const NOT_ON_LIST = [
  "OP07-045",
  "EB01-059",
  "ST06-015",
  "OP02-024",
  "OP03-098",
  "OP02-117",
  "OP05-041",
  "OP02-052",
  "P-163",
];

describe("official restriction data", () => {
  it("matches the current official banned cards, pairs, and empty restricted list", () => {
    const banned = RESTRICTION_ENTRIES.filter((entry) => entry.type === "banned").map((entry) => entry.card_id);
    const restricted = RESTRICTION_ENTRIES.filter((entry) => entry.type === "restricted");
    const pairs = RESTRICTION_ENTRIES.filter((entry) => entry.type === "pair").map((entry) => entry.card_ids);
    assert.deepEqual(banned, [
      "OP06-047",
      "OP03-040",
      "OP06-086",
      "ST10-001",
      "OP06-116",
      "OP14-020",
    ]);
    assert.deepEqual([...banned].sort(), BANNED);
    assert.deepEqual(restricted, []);
    assert.deepEqual(pairs, PAIRS);
    for (const id of NOT_ON_LIST) {
      assert.equal(
        RESTRICTION_ENTRIES.some((entry) => entry.card_id === id || entry.card_ids?.includes(id)),
        false,
        id,
      );
    }
    const mihawk = RESTRICTION_ENTRIES.find((entry) => entry.card_id === "OP14-020");
    assert.equal(mihawk?.effective_date, "2026-10-12");
    assert.equal(mihawk?.source_url, "https://en.onepiece-cardgame.com/news/restriction-261001.html");
    for (const entry of RESTRICTION_ENTRIES) {
      assert.match(entry.effective_date, /^\d{4}-\d{2}-\d{2}$/);
      assert.match(entry.source_url, /^https:\/\/(en|asia-en)\.onepiece-cardgame\.com\//);
    }
  });
});

describe("banned card badge", () => {
  it("shows the effective date in Traditional, Simplified, and English", () => {
    assert.equal(bannedBadgeText("OP14-020", "zh-Hant"), "2026-10-12 起禁用");
    assert.equal(bannedBadgeText("OP14-020", "zh-Hans"), "2026-10-12 起禁用");
    assert.equal(bannedBadgeText("OP14-020", "en"), "Banned from 2026-10-12");
    assert.equal(bannedBadgeText("OP14-020-P1", "en"), "Banned from 2026-10-12");
    assert.equal(bannedBadgeText("op14-020-p1", "zh-Hant"), "2026-10-12 起禁用");
    assert.equal(bannedBadgeText("OP11-040", "en"), null);
    assert.equal(bannedBadgeText("OP01-016", "zh-Hant"), null);
  });

  it("keeps Simplified as the OpenCC conversion of the Traditional phrase", () => {
    const convert = OpenCC.Converter({ from: "tw", to: "cn" });
    for (const key of [
      "detail.banned_from",
      "detail.restricted_from",
      "deck.warn_banned",
      "deck.warn_restricted",
      "deck.warn_pair",
    ]) {
      assert.equal(zhHans[key], convert(zhHant[key]), key);
      assert.ok(en[key], key);
    }
    const vars = { id: "OP14-020", a: "OP11-040", b: "OP11-067", date: "2026-10-12" };
    assert.equal(
      restrictionPhrase("zh-Hans", "deck.warn_pair", vars),
      convert(restrictionPhrase("zh-Hant", "deck.warn_pair", vars)),
    );
  });
});

describe("deck builder restriction warnings", () => {
  it("warns for a banned card, its alt art, and a banned pair", () => {
    const banned = deckRestrictionWarnings("OP14-020", { "OP01-016": 4 }, "en", "2026-10-13");
    assert.equal(banned.length, 1);
    assert.equal(banned[0]?.kind, "banned");
    assert.match(banned[0]?.text || "", /OP14-020/);
    assert.match(banned[0]?.text || "", /2026-10-12/);

    const alt = deckRestrictionWarnings("ST01-001", { "OP06-047-P1": 1 }, "zh-Hant", "2026-10-13");
    assert.equal(alt[0]?.kind, "banned");
    assert.match(alt[0]?.text || "", /OP06-047-P1/);
    assert.match(alt[0]?.text || "", /2026-04-01 起禁用/);

    const pair = deckRestrictionWarnings("OP11-040-P1", { "OP11-067": 2 }, "en", "2026-10-13");
    assert.equal(pair.length, 1);
    assert.equal(pair[0]?.kind, "pair");
    assert.match(pair[0]?.text || "", /OP11-040-P1/);
    assert.match(pair[0]?.text || "", /OP11-067/);

    assert.deepEqual(deckRestrictionWarnings("OP11-040", { "OP01-016": 4 }, "en", "2026-10-13"), []);
    assert.deepEqual(deckRestrictionWarnings("ST01-001", { "OP11-067": 4 }, "en", "2026-10-13"), []);
    assert.deepEqual(
      deckRestrictionWarnings("OP14-020", {}, "en", "2026-10-11").map((row) => row.kind),
      [],
    );
  });

  it("warns when a restricted card would exceed one copy", () => {
    const entries = [
      {
        card_id: "OP01-016",
        type: "restricted" as const,
        effective_date: "2026-01-01",
        source_url: "https://en.onepiece-cardgame.com/news/restriction.html",
      },
    ];
    assert.deepEqual(
      deckRestrictionWarnings("ST01-001", { "OP01-016": 1 }, "en", "2026-10-13", entries),
      [],
    );
    const over = deckRestrictionWarnings(
      "ST01-001",
      { "OP01-016": 1, "OP01-016-P1": 1 },
      "en",
      "2026-10-13",
      entries,
    );
    assert.equal(over.length, 1);
    assert.equal(over[0]?.kind, "restricted");
    assert.match(over[0]?.text || "", /OP01-016/);
  });
});
