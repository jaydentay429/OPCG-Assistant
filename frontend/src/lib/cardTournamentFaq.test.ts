import assert from "node:assert/strict";
import test from "node:test";
import { faqPageJsonLd } from "./seo.ts";
import {
  tournamentFaqAnswer,
  tournamentFaqLabel,
  uniqueTournamentFaqLabels,
  type TournamentFaqAppearance,
} from "./cardTournamentFaq.ts";

const JAPAN =
  "Japan: OP-14 Deck List – The Seven Warlords of the Sea（羅布・路基）";
const ENGLISH_LUCCI =
  "English: OP-12 Deck List – Legacy of The Master（羅布・路基）";
const ENGLISH_SAKAZUKI =
  "English: OP-12 Deck List – Legacy of The Master（盃）";

/** Two decks from the same meta, different dates and ids, same FAQ label. */
const DUPLICATE_WINDOW: TournamentFaqAppearance[] = [
  {
    meta_title: "Japan: OP-14 Deck List – The Seven Warlords of the Sea",
    leader_name: "羅布・路基",
  },
  {
    meta_title: "Japan: OP-14 Deck List – The Seven Warlords of the Sea",
    leader_name: "羅布・路基",
  },
  {
    meta_title: "English: OP-12 Deck List – Legacy of The Master",
    leader_name: "羅布・路基",
  },
  {
    meta_title: "English: OP-12 Deck List – Legacy of The Master",
    leader: "OP05-041",
    leader_name: "盃",
  },
];

test("duplicate tournament labels appear once and keep first-seen order", () => {
  const labels = uniqueTournamentFaqLabels(DUPLICATE_WINDOW);
  assert.deepEqual(labels, [JAPAN, ENGLISH_LUCCI]);
  assert.equal(labels.filter((label) => label === JAPAN).length, 1);

  const answer = tournamentFaqAnswer(DUPLICATE_WINDOW);
  assert.equal(
    answer,
    `本站公開賽事資料中出現於：${JAPAN}、${ENGLISH_LUCCI}。`,
  );
  assert.equal(answer.split(JAPAN).length - 1, 1);
});

test("labels that differ only by surrounding whitespace count as one", () => {
  const rows: TournamentFaqAppearance[] = [
    {
      meta_title: "  Japan: OP-14 Deck List – The Seven Warlords of the Sea",
      leader_name: "羅布・路基",
    },
    {
      meta_title: "Japan: OP-14 Deck List – The Seven Warlords of the Sea",
      leader_name: "羅布・路基",
    },
    {
      meta_title: "English: OP-12 Deck List – Legacy of The Master",
      leader_name: "羅布・路基",
    },
  ];
  assert.deepEqual(uniqueTournamentFaqLabels(rows), [
    `  ${JAPAN}`,
    ENGLISH_LUCCI,
  ]);
});

test("unique tournament labels stay in their original order and wording", () => {
  const rows: TournamentFaqAppearance[] = [
    { meta_title: "Event A", leader_name: "領袖甲" },
    { format: "jp", leader: "OP07-079" },
    { leader_name: "" },
    { meta_title: "Event D", leader_name: "領袖丁" },
  ];
  const before = rows.slice(0, 3).map(tournamentFaqLabel);
  assert.deepEqual(before, ["Event A（領袖甲）", "jp（OP07-079）", "賽事"]);
  assert.deepEqual(uniqueTournamentFaqLabels(rows), before);
  assert.equal(uniqueTournamentFaqLabels(rows).includes("Event D（領袖丁）"), false);
  assert.equal(
    tournamentFaqAnswer(rows),
    "本站公開賽事資料中出現於：Event A（領袖甲）、jp（OP07-079）、賽事。",
  );
});

test("same meta with a different leader stays in the list", () => {
  const rows = DUPLICATE_WINDOW.slice(2);
  assert.deepEqual(uniqueTournamentFaqLabels(rows), [ENGLISH_LUCCI, ENGLISH_SAKAZUKI]);
});

test("visible FAQ answer and FAQPage acceptedAnswer stay identical", () => {
  const question = "羅布・路基（OP05-093）常見於哪些賽事卡組？";
  const answer = tournamentFaqAnswer(DUPLICATE_WINDOW);
  const ld = faqPageJsonLd([{ question, answer }]);
  assert.ok(ld);
  const entity = (ld.mainEntity as Array<{ name: string; acceptedAnswer: { text: string } }>)[0];
  assert.equal(entity.name, question);
  assert.equal(entity.acceptedAnswer.text, answer);
  assert.equal(answer.includes(`${JAPAN}、${JAPAN}`), false);
});
