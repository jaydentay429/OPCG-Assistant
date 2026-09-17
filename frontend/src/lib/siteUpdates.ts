import type { Lang } from "@/lib/i18n";

export type SiteUpdateKind = "fix" | "feature";

export type SiteUpdate = {
  id: string;
  date: string;
  kind: SiteUpdateKind;
  href?: string;
  title: Record<Lang, string>;
  body: Record<Lang, string>;
};

/** Newest first. Keep this list short — homepage shows the latest few. */
export const SITE_UPDATES: SiteUpdate[] = [
  {
    id: "eb05-037-black-maria",
    date: "2026-09-17",
    kind: "feature",
    href: "/cards/EB05-037",
    title: {
      "zh-Hant": "EB05-037 黑瑪麗亞加入卡表",
      "zh-Hans": "EB05-037 黑玛丽亚加入卡表",
      en: "EB05-037 Black Maria added",
    },
    body: {
      "zh-Hant": "登場時查看卡組上3張，公開最多1張《百獸海賊團》加入手牌，其餘放回卡組下面。",
      "zh-Hans": "登场时查看卡组上3张，公开最多1张《百兽海贼团》加入手牌，其余放回卡组下面。",
      en: "On Play, look at the top 3 of your deck; reveal up to 1 Animal Kingdom Pirates card to hand, rest to the bottom.",
    },
  },
  {
    id: "eb05-028-hancock",
    date: "2026-09-16",
    kind: "feature",
    href: "/cards/EB05-028",
    title: {
      "zh-Hant": "EB05-028 波雅・漢考克加入卡表",
      "zh-Hans": "EB05-028 波雅・汉考克加入卡表",
      en: "EB05-028 Boa Hancock added",
    },
    body: {
      "zh-Hant": "登場時若對手手牌有9張以上，對手廢棄4張自身手牌。",
      "zh-Hans": "登场时若对手手牌有9张以上，对手弃置4张自身手牌。",
      en: "On Play, if the opponent has 9 or more cards in hand, they trash 4 cards from their hand.",
    },
  },
  {
    id: "yuyu-daily-family-sweep",
    date: "2026-09-15",
    kind: "fix",
    href: "/prices",
    title: {
      "zh-Hant": "日價改為全庫每日對齊遊々亭",
      "zh-Hans": "日价改为全库每日对齐游々亭",
      en: "Yen prices now refresh the whole catalog each day",
    },
    body: {
      "zh-Hant": "每個基礎號一天搜一次並寫入全部異圖；對不上的殘留現價會清掉，429 則保留舊價下午續跑。",
      "zh-Hans": "每个基础号一天搜一次并写入全部异图；对不上的残留现价会清掉，429 则保留旧价下午续跑。",
      en: "Each base ID is searched once a day for every parallel; unmatched leftover prices are cleared, while 429s keep the old price and resume later.",
    },
  },
  {
    id: "op08-001-p2-foil-price",
    date: "2026-09-15",
    kind: "fix",
    href: "/prices",
    title: {
      "zh-Hant": "修正 OP08-001 箔押し日價",
      "zh-Hans": "修正 OP08-001 箔押し日价",
      en: "Fixed OP08-001 foil yen price",
    },
    body: {
      "zh-Hant": "EB-02 喬巴箔押し不再沿用 148000，改對上游々亭 ¥59800。",
      "zh-Hans": "EB-02 乔巴箔押し不再沿用 148000，改对上游々亭 ¥59800。",
      en: "The EB-02 Chopper foil no longer keeps 148000; it now maps to Yuyu-tei ¥59800.",
    },
  },
  {
    id: "op07-038-p2-foil-price",
    date: "2026-09-15",
    kind: "fix",
    href: "/prices",
    title: {
      "zh-Hant": "修正 OP07-038 箔押し日價",
      "zh-Hans": "修正 OP07-038 箔押し日价",
      en: "Fixed OP07-038 foil yen price",
    },
    body: {
      "zh-Hant": "EB-02 漢考克箔押し不再沿用 248000，改對上游々亭 ¥99800。",
      "zh-Hans": "EB-02 汉库克箔押し不再沿用 248000，改对上游々亭 ¥99800。",
      en: "The EB-02 Hancock foil no longer keeps 248000; it now maps to Yuyu-tei ¥99800.",
    },
  },
  {
    id: "yuyu-miss-retry-needles",
    date: "2026-09-15",
    kind: "fix",
    href: "/prices",
    title: {
      "zh-Hant": "補抓先前漏掉的日價",
      "zh-Hans": "补抓先前漏掉的日价",
      en: "Filled in yen prices that the matcher used to skip",
    },
    body: {
      "zh-Hant": "再版與推廣異圖只要套名對得上遊々亭，不再因「已知無價」被每日任務跳過。",
      "zh-Hans": "再版与推广异图只要套名对得上游々亭，不再因「已知无价」被每日任务跳过。",
      en: "Reprint and promo parallels that uniquely match a Yuyu-tei set name are retried daily instead of staying unpriced.",
    },
  },
  {
    id: "p-105-p2-sp-price",
    date: "2026-09-15",
    kind: "fix",
    href: "/prices",
    title: {
      "zh-Hant": "補上 P-105 SP 日價",
      "zh-Hans": "补上 P-105 SP 日价",
      en: "Filled in P-105 SP yen price",
    },
    body: {
      "zh-Hant": "OP-15 薩波 SP 先前一直顯示暫無報價，現已對上游々亭 ¥5980；介面只顯示 P-105。",
      "zh-Hans": "OP-15 萨波 SP 先前一直显示暂无报价，现已对上游々亭 ¥5980；界面只显示 P-105。",
      en: "The OP-15 Sabo SP was stuck as unpriced; it now maps to Yuyu-tei ¥5980 and shows as P-105.",
    },
  },
  {
    id: "p-084-p1-sp-price-id",
    date: "2026-09-15",
    kind: "fix",
    href: "/prices",
    title: {
      "zh-Hant": "補上 P-084 SP 日價並隱藏異圖後綴",
      "zh-Hans": "补上 P-084 SP 日价并隐藏异图后缀",
      en: "Filled in P-084 SP yen price and hid the -P1 suffix",
    },
    body: {
      "zh-Hant": "OP-17 巴其金框 SP 現對上游々亭 ¥19800；推廣卡異圖只顯示 P-084，不再露出 -P1。",
      "zh-Hans": "OP-17 巴基金框 SP 现对上游々亭 ¥19800；推广卡异图只显示 P-084，不再露出 -P1。",
      en: "The OP-17 Buggy gold SP now maps to Yuyu-tei ¥19800, and promo parallels show as P-084 without -P1.",
    },
  },
  {
    id: "op13-028-p2-sp-price",
    date: "2026-09-15",
    kind: "fix",
    href: "/prices",
    title: {
      "zh-Hant": "補上 OP13-028 SP 日價",
      "zh-Hans": "补上 OP13-028 SP 日价",
      en: "Filled in OP13-028 SP yen price",
    },
    body: {
      "zh-Hant": "OP-17 香克斯金框 SP 先前一直顯示暫無報價，現已對上游々亭 ¥34800。",
      "zh-Hans": "OP-17 香克斯金框 SP 先前一直显示暂无报价，现已对上游々亭 ¥34800。",
      en: "The OP-17 Shanks gold SP was stuck as unpriced; it now maps to Yuyu-tei ¥34800.",
    },
  },
  {
    id: "op09-093-p2-manga-price",
    date: "2026-09-15",
    kind: "fix",
    href: "/prices",
    title: {
      "zh-Hant": "修正 OP09-093 漫畫閃日價",
      "zh-Hans": "修正 OP09-093 漫画闪日价",
      en: "Fixed OP09-093 manga yen price",
    },
    body: {
      "zh-Hant": "汀奇漫畫閃不再沿用 178000，改對上游々亭超級平行 ¥148000。",
      "zh-Hans": "汀奇漫画闪不再沿用 178000，改对上游々亭超级平行 ¥148000。",
      en: "Blackbeard’s manga rare no longer keeps 178000; it now maps to Yuyu-tei’s super parallel ¥148000.",
    },
  },
  {
    id: "op09-051-manga-silver-price",
    date: "2026-09-15",
    kind: "fix",
    href: "/prices",
    title: {
      "zh-Hant": "修正 OP09-051 漫畫閃／銀 SP 日價",
      "zh-Hans": "修正 OP09-051 漫画闪／银 SP 日价",
      en: "Fixed OP09-051 manga and silver SP yen prices",
    },
    body: {
      "zh-Hant": "漫畫閃與 OP-14 銀框不再共用 128000，分別對上游々亭 ¥99800／¥79800。",
      "zh-Hans": "漫画闪与 OP-14 银框不再共用 128000，分别对上游々亭 ¥99800／¥79800。",
      en: "Manga and OP-14 silver SP no longer share 128000; they now map to Yuyu-tei ¥99800 / ¥79800.",
    },
  },
  {
    id: "st06-006-p2-sp-price",
    date: "2026-09-15",
    kind: "fix",
    href: "/prices",
    title: {
      "zh-Hant": "補上 ST06-006 SP 日價",
      "zh-Hans": "补上 ST06-006 SP 日价",
      en: "Filled in ST06-006 SP yen price",
    },
    body: {
      "zh-Hant": "OP-08 達絲琪 SP 先前一直顯示暫無報價，現已對上游々亭 ¥5980。",
      "zh-Hans": "OP-08 达丝琪 SP 先前一直显示暂无报价，现已对上游々亭 ¥5980。",
      en: "The OP-08 Tashigi SP was stuck as unpriced; it now maps to Yuyu-tei ¥5980.",
    },
  },
  {
    id: "st31-004-p1-sp-price",
    date: "2026-09-15",
    kind: "fix",
    href: "/prices",
    title: {
      "zh-Hant": "補上 ST31-004 SP 日價",
      "zh-Hans": "补上 ST31-004 SP 日价",
      en: "Filled in ST31-004 SP yen price",
    },
    body: {
      "zh-Hant": "OP-17 金框 SP 先前一直顯示暫無報價，現已對上游々亭 ¥99800。",
      "zh-Hans": "OP-17 金框 SP 先前一直显示暂无报价，现已对上游々亭 ¥99800。",
      en: "The OP-17 gold SP was stuck as unpriced; it now maps to Yuyu-tei ¥99800.",
    },
  },
  {
    id: "st27-005-p1-sp-price",
    date: "2026-09-15",
    kind: "fix",
    href: "/prices",
    title: {
      "zh-Hant": "補上 ST27-005 SP 日價",
      "zh-Hans": "补上 ST27-005 SP 日价",
      en: "Filled in ST27-005 SP yen price",
    },
    body: {
      "zh-Hant": "OP-17 金框 SP 先前一直顯示暫無報價，現已對上游々亭 ¥29800。",
      "zh-Hans": "OP-17 金框 SP 先前一直显示暂无报价，现已对上游々亭 ¥29800。",
      en: "The OP-17 gold SP was stuck as unpriced; it now maps to Yuyu-tei ¥29800.",
    },
  },
  {
    id: "op05-119-p7-gold-sp-price",
    date: "2026-09-15",
    kind: "fix",
    href: "/prices",
    title: {
      "zh-Hant": "修正 OP05-119 金 SP 日價",
      "zh-Hans": "修正 OP05-119 金 SP 日价",
      en: "Fixed OP05-119 gold SP yen price",
    },
    body: {
      "zh-Hant": "OP-11 金框 SP 不再誤用漫畫閃 798000，改對上游々亭金平行 ¥1280000。",
      "zh-Hans": "OP-11 金框 SP 不再误用漫画闪 798000，改对上游々亭金平行 ¥1280000。",
      en: "The OP-11 gold SP no longer inherits the manga 798000; it now maps to Yuyu-tei’s gold parallel ¥1280000.",
    },
  },
  {
    id: "op05-119-p3-prb-price",
    date: "2026-09-15",
    kind: "fix",
    href: "/prices",
    title: {
      "zh-Hant": "修正 OP05-119 PRB 再版日價",
      "zh-Hans": "修正 OP05-119 PRB 再版日价",
      en: "Fixed OP05-119 PRB reprint yen price",
    },
    body: {
      "zh-Hant": "THE BEST（PRB-01）再版不再沿用 12800，改對上游々亭 (PRB) ¥7980。",
      "zh-Hans": "THE BEST（PRB-01）再版不再沿用 12800，改对上游々亭 (PRB) ¥7980。",
      en: "The PRB-01 Gear 5 reprint now maps to Yuyu-tei’s (PRB) ¥7980 instead of a stale 12800.",
    },
  },
  {
    id: "p-rarity-price-sync",
    date: "2026-09-15",
    kind: "fix",
    href: "/prices",
    title: {
      "zh-Hant": "補上 P 推廣卡日價",
      "zh-Hans": "补上 P 推广卡日价",
      en: "Promo P-rarity yen prices now sync from Yuyu-tei",
    },
    body: {
      "zh-Hant": "P 稀有度先前被日更當成永久無價跳過；現已對上游々亭 P 區與 25 週年／7-11 等列名。",
      "zh-Hans": "P 稀有度先前被日更当成永久无价跳过；现已对上游々亭 P 区与 25 周年／7-11 等列名。",
      en: "Promo P cards were skipped after the first miss; they now match Yuyu-tei’s P list and named parallels.",
    },
  },
  {
    id: "sp-price-refresh",
    date: "2026-09-15",
    kind: "fix",
    href: "/prices",
    title: {
      "zh-Hant": "修正 SP 卡日價對不上遊々亭",
      "zh-Hans": "修正 SP 卡日价对不上游々亭",
      en: "Fixed stale Yuyu-tei prices on SP cards",
    },
    body: {
      "zh-Hant": "SP 再版改以系列頁／稀有度分區對價，不再沿用對不上圖時留下的舊標。",
      "zh-Hans": "SP 再版改以系列页／稀有度分区对价，不再沿用对不上图时留下的旧标。",
      en: "SP reprints now match Yuyu-tei by set page and rarity section instead of leftover stale prices.",
    },
  },
  {
    id: "op13-042-price-split",
    date: "2026-09-15",
    kind: "fix",
    href: "/prices",
    title: {
      "zh-Hant": "修正 OP13-042 各版本日價",
      "zh-Hans": "修正 OP13-042 各版本日价",
      en: "Fixed OP13-042 variant yen prices",
    },
    body: {
      "zh-Hant": "OP-15 SP／OP-13 異圖／原畫不再沿用過期標價，分別對上遊々亭 9980／1280／220。",
      "zh-Hans": "OP-15 SP／OP-13 异图／原画不再沿用过期标价，分别对上游々亭 9980／1280／220。",
      en: "OP-15 SP, OP-13 alt art, and base now map to current Yuyu-tei 9980 / 1280 / 220.",
    },
  },
  {
    id: "st21-001-price-split",
    date: "2026-09-15",
    kind: "fix",
    href: "/prices",
    title: {
      "zh-Hant": "修正 ST21-001 各版本日價",
      "zh-Hans": "修正 ST21-001 各版本日价",
      en: "Fixed ST21-001 variant yen prices",
    },
    body: {
      "zh-Hant": "原畫／BASE SHOP 限定／ST-31 再版不再共用最低價，分別對上遊々亭標價。",
      "zh-Hans": "原画／BASE SHOP 限定／ST-31 再版不再共用最低价，分别对上游々亭标价。",
      en: "Base, BASE SHOP limited, and ST-31 reprint now map to their own Yuyu-tei prices.",
    },
  },
  {
    id: "eb05-044-ms-fathers-day",
    date: "2026-09-15",
    kind: "feature",
    href: "/cards/EB05-044",
    title: {
      "zh-Hant": "EB05-044 Miss父親節加入卡表",
      "zh-Hans": "EB05-044 Miss父亲节加入卡表",
      en: "EB05-044 Ms. Father's Day added",
    },
    body: {
      "zh-Hant": "登場時若自己領袖有 B・W 且對手有費用 0 角色，對手領袖本回合力量 −1000。",
      "zh-Hans": "登场时若自己领袖有 B・W 且对手有费用 0 角色，对手领袖本回合力量 −1000。",
      en: "On Play: if your Leader is Baroque Works and the opponent has a cost 0 Character, their Leader gets −1000 this turn.",
    },
  },
  {
    id: "eb05-012-camie",
    date: "2026-09-14",
    kind: "feature",
    href: "/cards/EB05-012",
    title: {
      "zh-Hant": "EB05-012 海咪加入卡表",
      "zh-Hans": "EB05-012 海咪加入卡表",
      en: "EB05-012 Camie added",
    },
    body: {
      "zh-Hant": "登場時可將最多 1 張對手費用 6 以下的角色卡置為休息。",
      "zh-Hans": "登场时可将最多 1 张对手费用 6 以下的角色卡置为休息。",
      en: "On Play: rest up to 1 of your opponent's Characters with a cost of 6 or less.",
    },
  },
  {
    id: "op11-040-search-dest",
    date: "2026-09-13",
    kind: "fix",
    href: "/play",
    title: {
      "zh-Hant": "修復魯夫領袖檢索後無法排牌疊",
      "zh-Hans": "修复路飞领袖检索后无法排牌叠",
      en: "Fixed Luffy leader search stuck before deck order",
    },
    body: {
      "zh-Hant": "選卡後會先問放到卡組上或下，再依序排列其餘卡片（OP11-040 等）。",
      "zh-Hans": "选卡后会先问放到卡组上或下，再依序排列其余卡片（OP11-040 等）。",
      en: "After picking a card, you can now choose top or bottom, then order the rest (OP11-040 and similar).",
    },
  },
  {
    id: "eb05-027-hibari",
    date: "2026-09-13",
    kind: "feature",
    href: "/cards/EB05-027",
    title: {
      "zh-Hant": "EB05-027 雲雀加入卡表",
      "zh-Hans": "EB05-027 云雀加入卡表",
      en: "EB05-027 Hibari added",
    },
    body: {
      "zh-Hant": "登場時抽 3 張並廢棄 2 張手牌，然後可將最多 1 張費用 2 以下的角色卡放到持有者牌組底。",
      "zh-Hans": "登场时抽 3 张并废弃 2 张手牌，然后可将最多 1 张费用 2 以下的角色卡放到持有者牌组底。",
      en: "On Play: draw 3 and trash 2 from hand, then you may put a cost 2 or less Character on the owner's deck bottom.",
    },
  },
  {
    id: "eb05-057-nojiko",
    date: "2026-09-11",
    kind: "feature",
    href: "/cards/EB05-057",
    title: {
      "zh-Hant": "EB05-057 虹子加入卡表",
      "zh-Hans": "EB05-057 虹子加入卡表",
      en: "EB05-057 Nojiko added",
    },
    body: {
      "zh-Hant": "啟動主要每回合 1 次：將最多 1 張休息咚給予自己《特》或《知》的領航／角色。生命 2 以下時，觸發器可使手牌 6000 以下的觸發器角色登場。",
      "zh-Hans": "启动主要每回合 1 次：将最多 1 张休息咚给予自己《特》或《知》的领航／角色。生命 2 以下时，触发器可使手牌 6000 以下的触发器角色登场。",
      en: "Once per turn, attach up to 1 rested DON!! to your Special or Wisdom Leader/Character. Trigger: if Life ≤2, play a 6000-or-less Trigger Character from hand.",
    },
  },
  {
    id: "eb05-047-ripley",
    date: "2026-09-10",
    kind: "feature",
    href: "/cards/EB05-047",
    title: {
      "zh-Hant": "EB05-047 莉普莉加入卡表",
      "zh-Hans": "EB05-047 莉普莉加入卡表",
      en: "EB05-047 Ripley added",
    },
    body: {
      "zh-Hant": "這張角色卡費用+12。登場時可廢棄 1 張手牌，使廢棄區最多 1 張費用 2 以下的角色卡登場。",
      "zh-Hans": "这张角色卡费用+12。登场时可废弃 1 张手牌，使废弃区最多 1 张费用 2 以下的角色卡登场。",
      en: "This Character gains +12 cost. On Play you may trash 1 from hand to play a cost 2 or less Character from trash.",
    },
  },
  {
    id: "op09-001-shanks-leader-debuff",
    date: "2026-09-10",
    kind: "fix",
    href: "/play",
    title: {
      "zh-Hant": "紅髮領航可減對方領航卡力量",
      "zh-Hans": "红发领航可减对方领航卡力量",
      en: "Shanks can now −1000 the opponent Leader",
    },
    body: {
      "zh-Hant": "異圖香克斯對手攻擊時可選對方領航卡或角色卡，該回合力量−1000。",
      "zh-Hans": "异图香克斯对手攻击时可选对方领航卡或角色卡，该回合力量−1000。",
      en: "Parallel Shanks On Opponent's Attack can target the opponent Leader or a Character for −1000.",
    },
  },
  {
    id: "eb05-002-doll",
    date: "2026-09-09",
    kind: "feature",
    href: "/cards/EB05-002",
    title: {
      "zh-Hant": "EB05-002 朵爾加入卡表",
      "zh-Hans": "EB05-002 朵尔加入卡表",
      en: "EB05-002 Doll added",
    },
    body: {
      "zh-Hant": "登場時查看牌組頂 5 張，加入最多 2 張費用 2 以上的海軍，然後廢棄 1 張手牌。",
      "zh-Hans": "登场时查看牌组顶 5 张，加入最多 2 张费用 2 以上的海军，然后废弃 1 张手牌。",
      en: "On Play: look at 5, add up to 2 Navy with cost 2 or more, then trash 1 from hand.",
    },
  },
  {
    id: "play-life-count",
    date: "2026-09-08",
    kind: "feature",
    href: "/play",
    title: {
      "zh-Hant": "對戰生命區顯示剩餘血量",
      "zh-Hans": "对战生命区显示剩余血量",
      en: "Life remaining shown on the board",
    },
    body: {
      "zh-Hant": "生命區中央會顯示還剩幾點生命，方便一眼確認。",
      "zh-Hans": "生命区中央会显示还剩几点生命，方便一眼确认。",
      en: "The life zone now shows remaining life in the center of the stack.",
    },
  },
  {
    id: "op16-001-p2-rush",
    date: "2026-09-08",
    kind: "fix",
    href: "/play",
    title: {
      "zh-Hant": "艾斯異圖領航可賦予速攻",
      "zh-Hans": "艾斯异图领航可赋予速攻",
      en: "Ace parallel leader Rush now works",
    },
    body: {
      "zh-Hant": "OP16-001-P2 打出 8 費白鬍子後，啟動主要可以正常賦予【速攻】。",
      "zh-Hans": "OP16-001-P2 打出 8 费白胡子后，启动主要可以正常赋予【速攻】。",
      en: "OP16-001-P2 can grant Rush after you play an 8-cost Whitebeard.",
    },
  },
  {
    id: "op17-058-once",
    date: "2026-09-08",
    kind: "fix",
    href: "/play",
    title: {
      "zh-Hant": "海道每回合 1 次在對手回合可再用",
      "zh-Hans": "海道每回合 1 次在对手回合可再用",
      en: "Kaido once-per-turn resets on opponent turn",
    },
    body: {
      "zh-Hant": "【每回合1次】會在對手回合開始時重置，對方攻擊時效果可再發動。",
      "zh-Hans": "【每回合1次】会在对手回合开始时重置，对方攻击时效果可再发动。",
      en: "[Once Per Turn] now clears when the opponent's turn starts.",
    },
  },
];

export const SITE_UPDATES_LIMIT = 5;

export function latestSiteUpdates(limit = SITE_UPDATES_LIMIT): SiteUpdate[] {
  return SITE_UPDATES.slice(0, limit);
}

export function formatUpdateDate(date: string, lang: Lang): string {
  const [y, m, d] = date.split("-");
  if (!y || !m || !d) return date;
  if (lang === "en") return `${y}-${m}-${d}`;
  return `${y}/${m}/${d}`;
}
