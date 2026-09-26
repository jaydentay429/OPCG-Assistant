import assert from "node:assert/strict";
import test from "node:test";
import { breadcrumbJsonLd, cardJsonLd, jsonLdScript, rootJsonLd, visibleCardEffect } from "./seo.ts";

test("root JSON-LD keeps organization data and has no FAQPage", () => {
  const raw = jsonLdScript(rootJsonLd());
  assert.equal(raw.includes("FAQPage"), false);
  assert.match(raw, /"@type":"Organization"/);
  assert.match(raw, /"@type":"WebSite"/);
  assert.match(raw, /"@type":"WebApplication"/);
  assert.match(raw, /"@type":"SearchAction"/);
});

test("strips a sitewide FAQPage node out of @graph", () => {
  const graph = rootJsonLd();
  (graph["@graph"] as unknown[]).push({
    "@type": "FAQPage",
    "@id": "https://optcgassistant.com/#faq",
    mainEntity: [
      {
        "@type": "Question",
        name: "OPCG 卡牌助手是官方網站嗎？",
        acceptedAnswer: { "@type": "Answer", text: "不是。" },
      },
    ],
  });
  const raw = jsonLdScript(graph);
  assert.equal(raw.includes("FAQPage"), false);
  assert.equal(raw.includes("官方網站嗎"), false);
  assert.match(raw, /"@type":"Organization"/);
  assert.match(raw, /"@type":"WebApplication"/);
});

test("card schema drops FAQPage unless that page opts in, and then keeps only one", () => {
  const payload = [
    cardJsonLd({
      id: "OP05-093",
      name: "羅布・路基",
      description: "效果文本",
      rarity: "SR",
      series: "OP05",
    }),
    breadcrumbJsonLd([
      { name: "首頁", path: "/" },
      { name: "卡牌搜索", path: "/search" },
      { name: "羅布・路基（OP05-093）", path: "/cards/OP05-093" },
    ]),
    {
      "@context": "https://schema.org",
      "@type": "FAQPage",
      mainEntity: [
        {
          "@type": "Question",
          name: "這張卡的卡號是什麼？",
          acceptedAnswer: { "@type": "Answer", text: "OP05-093" },
        },
      ],
    },
    {
      "@context": "https://schema.org",
      "@type": "FAQPage",
      mainEntity: [
        {
          "@type": "Question",
          name: "第二段不該出現",
          acceptedAnswer: { "@type": "Answer", text: "重複" },
        },
      ],
    },
  ];
  const hidden = jsonLdScript(payload);
  assert.equal(hidden.includes("FAQPage"), false);
  assert.match(hidden, /"@type":"Product"/);
  assert.match(hidden, /"name":"Set","value":"OP05"/);

  const shown = jsonLdScript(payload, { allowFaq: true });
  assert.equal(shown.split('"@type":"FAQPage"').length - 1, 1);
  assert.match(shown, /這張卡的卡號是什麼/);
  assert.equal(shown.includes("第二段不該出現"), false);
  assert.match(shown, /"@type":"Product"/);
  assert.match(shown, /"@type":"BreadcrumbList"/);
});

test("empty card effects are not FAQ answers", () => {
  assert.equal(visibleCardEffect(""), "");
  assert.equal(visibleCardEffect("-"), "");
  assert.equal(visibleCardEffect(" — "), "");
  assert.equal(visibleCardEffect("（暫無效果文本）"), "");
  assert.equal(visibleCardEffect("【登場時】抽 1 張。"), "【登場時】抽 1 張。");
});

test("a page with a visible FAQ can still opt in to one FAQPage", () => {
  const raw = jsonLdScript(
    {
      "@context": "https://schema.org",
      "@type": "FAQPage",
      mainEntity: [
        {
          "@type": "Question",
          name: "這是官方網站嗎？",
          acceptedAnswer: { "@type": "Answer", text: "不是。本站是粉絲工具。" },
        },
      ],
    },
    { allowFaq: true },
  );
  assert.match(raw, /"@type":"FAQPage"/);
  assert.match(raw, /這是官方網站嗎/);
});
