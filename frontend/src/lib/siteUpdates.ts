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
    id: "op18-086-2026-09-26",
    date: "2026-09-26",
    kind: "feature",
    href: "/cards/OP18-086",
    title: {
      "zh-Hant": "OP18-086 戈爾德伯格 已上線",
      "zh-Hans": "OP18-086 戈尔德伯格 已上线",
      en: "OP18-086 Goldberg added",
    },
    body: {
      "zh-Hant": "黑 3 費 4000：這張角色費用 +12；【KO時】最多 KO 1 張對手費用 4 以下角色。",
      "zh-Hans": "黑 3 费 4000：这张角色费用 +12；【KO时】最多 KO 1 张对手费用 4 以下角色。",
      en: "Black 3c 4000: this Character +12 cost; On K.O. K.O. up to 1 opponent Character with cost 4 or less.",
    },
  },
  {
    id: "op18-066-2026-09-25",
    date: "2026-09-25",
    kind: "feature",
    href: "/cards/OP18-066",
    title: {
      "zh-Hant": "OP18-066 贊拜 已上線",
      "zh-Hans": "OP18-066 赞拜 已上线",
      en: "OP18-066 Zambai added",
    },
    body: {
      "zh-Hant": "紫 5 費 6000：啟動主要可 KO 1 張自己費用 5 以下舞台，這張卡本回合獲得【速攻】。",
      "zh-Hans": "紫 5 费 6000：启动主要可 KO 1 张自己费用 5 以下舞台，这张卡本回合获得【速攻】。",
      en: "Purple 5c 6000: Activate Main you may K.O. 1 of your cost≤5 Stages so this Character gains Rush this turn.",
    },
  },
  {
    id: "op18-056-2026-09-24",
    date: "2026-09-24",
    kind: "feature",
    href: "/cards/OP18-056",
    title: {
      "zh-Hant": "OP18-056 13號先生＆星期五小姐 已上線",
      "zh-Hans": "OP18-056 13号先生＆星期五小姐 已上线",
      en: "OP18-056 Mr.13 & Miss. Friday added",
    },
    body: {
      "zh-Hant": "綠 2 費 3000：咚‼×1 這張卡 +1000；登場可把另一張自己《B・W》放到卡組底，對手廢棄自身手牌 1 張。",
      "zh-Hans": "绿 2 费 3000：咚‼×1 这张卡 +1000；登场可把另一张自己《B・W》放到卡组底，对手废弃自身手牌 1 张。",
      en: "Green 2c 3000: DON!!×1 this Character +1000; On Play you may bottom another of your {Baroque Works} Characters so the opponent discards 1.",
    },
  },
  {
    id: "op14-033-deny-rest-two-2026-09-24",
    date: "2026-09-24",
    kind: "fix",
    href: "/play",
    title: {
      "zh-Hant": "OP14-033 佩羅娜登場可指定兩張",
      "zh-Hans": "OP14-033 佩罗娜登场可指定两张",
      en: "OP14-033 Perona On Play can lock two Characters",
    },
    body: {
      "zh-Hant": "【登場時】最多 2 張對手費用 5 以下角色無法休息，現可連續指定兩張，不再只鎖一張。",
      "zh-Hans": "【登场时】最多 2 张对手费用 5 以下角色无法休息，现可连续指定两张，不再只锁一张。",
      en: "On Play can now choose up to two opponent cost≤5 Characters that cannot rest, not only one.",
    },
  },
  {
    id: "eb05-046-2026-09-23",
    date: "2026-09-23",
    kind: "feature",
    href: "/cards/EB05-046",
    title: {
      "zh-Hant": "EB05-046 刺針刺蝟 已上線",
      "zh-Hans": "EB05-046 刺针刺猬 已上线",
      en: "EB05-046 Stinger Hedgehog added",
    },
    body: {
      "zh-Hant": "黑 1 費事件：可休息 1 咚並 KO 自己《B・W》角色，對手費用 0 角色此回合無法防禦；反擊領航 +3000。",
      "zh-Hans": "黑 1 费事件：可休息 1 咚并 KO 自己《B・W》角色，对手费用 0 角色此回合无法防御；反击领航 +3000。",
      en: "Black 1c Event: rest 1 DON!! and KO your {Baroque Works} Character so opponent cost-0 Characters cannot Blocker this turn; Counter: Leader +3000.",
    },
  },
  {
    id: "op18-026-2026-09-23",
    date: "2026-09-23",
    kind: "feature",
    href: "/cards/OP18-026",
    title: {
      "zh-Hant": "OP18-026 琪姆妮 已上線",
      "zh-Hans": "OP18-026 琪姆妮 已上线",
      en: "OP18-026 Chimney added",
    },
    body: {
      "zh-Hant": "綠 2 費 0 力量角色：可休息自己的「貢貝」與這張卡，把領航「蒙其・D・魯夫」置為活動。",
      "zh-Hans": "绿 2 费 0 力量角色：可休息自己的「贡贝」与这张卡，把领航「蒙其・D・鲁夫」置为活动。",
      en: "Green 2c 0-power Character: rest your [Gonbe] and this Character to set Leader [Monkey.D.Luffy] active.",
    },
  },
  {
    id: "hide-card-seo-dump-2026-09-22",
    date: "2026-09-22",
    kind: "fix",
    href: "/search",
    title: {
      "zh-Hant": "卡牌詳情頁去掉重複說明",
      "zh-Hans": "卡牌详情页去掉重复说明",
      en: "Card pages no longer show a duplicate text dump",
    },
    body: {
      "zh-Hant": "卡號、效果與常見問題改由原本詳情區顯示，頁頂那一大段說明已收起。",
      "zh-Hans": "卡号、效果与常见问题改由原本详情区显示，页顶那一大段说明已收起。",
      en: "The extra summary, facts, and FAQ block at the top of card pages is now hidden.",
    },
  },
  {
    id: "eb05-060-2026-09-22",
    date: "2026-09-22",
    kind: "feature",
    href: "/cards/EB05-060",
    title: {
      "zh-Hant": "EB05-060 「莉莉絲」拜託了!!! 已上線",
      "zh-Hans": "EB05-060 「莉莉丝」拜托了!!! 已上线",
      en: "EB05-060 I'm Counting on Lilith!!! added",
    },
    body: {
      "zh-Hant": "黃 1 費事件：可廢棄自己費用5以上《蛋頭》角色，將卡組頂加入生命；反擊翻開生命頂，領航或角色此戰鬥 +4000。",
      "zh-Hans": "黄 1 费事件：可废弃自己费用5以上《蛋头》角色，将卡组顶加入生命；反击翻开生命顶，领航或角色此战斗 +4000。",
      en: "Yellow 1c Event: you may trash a cost≥5 {Egghead} Character to add the deck top to Life; Counter: turn Life top face-up, Leader or Character +4000 this battle.",
    },
  },
  {
    id: "op18-003-2026-09-22",
    date: "2026-09-22",
    kind: "feature",
    href: "/cards/OP18-003",
    title: {
      "zh-Hant": "OP18-003 海貓 已上線",
      "zh-Hans": "OP18-003 海猫 已上线",
      en: "OP18-003 Sea Cat added",
    },
    body: {
      "zh-Hant": "紅 5 費 6000 力量角色，《動物／阿拉巴斯坦王國》，反擊 +2000。",
      "zh-Hans": "红 5 费 6000 力量角色，《动物／阿拉巴斯坦王国》，反击 +2000。",
      en: "Red 5c 6000-power Character, {Animal}/{Alabasta}, Counter +2000.",
    },
  },
  {
    id: "seo-ssr-community-2026-09-21",
    date: "2026-09-21",
    kind: "feature",
    href: "/",
    title: {
      "zh-Hant": "社區帖與卡牌頁更易被搜到",
      "zh-Hans": "社区帖与卡牌页更易被搜到",
      en: "Forum posts and card pages are easier to find",
    },
    body: {
      "zh-Hant": "帖文、價格與賽事說明會寫進第一次打開的網頁，方便搜尋與 AI 引用。",
      "zh-Hans": "帖文、价格与赛事说明会写进第一次打开的网页，方便搜索与 AI 引用。",
      en: "Thread text, price notes, and tournament copy now ship in the first HTML so search and AI can cite them.",
    },
  },
  {
    id: "eb05-009-2026-09-21",
    date: "2026-09-21",
    kind: "feature",
    href: "/cards/EB05-009",
    title: {
      "zh-Hant": "EB05-009 與我一起死吧!!! 已上線",
      "zh-Hans": "EB05-009 与我一起死吧!!! 已上线",
      en: "EB05-009 Let's Die Together!!! added",
    },
    body: {
      "zh-Hant": "紅 1 費事件：自己原本力量≤4000 角色全數 +1000 至對手結束階段；反擊時領航 +3000。",
      "zh-Hans": "红 1 费事件：自己原本力量≤4000 角色全数 +1000 至对手结束阶段；反击时领航 +3000。",
      en: "Red 1c Event: all your printed-power≤4000 Characters +1000 until the opponent's End Phase; Counter: Leader +3000.",
    },
  },
  {
    id: "seo-sets-hub-2026-09-21",
    date: "2026-09-21",
    kind: "feature",
    href: "/sets",
    title: {
      "zh-Hant": "系列卡表上線，搜尋更好找",
      "zh-Hans": "系列卡表上线，搜索更好找",
      en: "Set lists added for search",
    },
    body: {
      "zh-Hant": "可按 OP / EB / ST 彈次瀏覽全卡表；首頁與頁尾補上對戰、組牌等連結。",
      "zh-Hans": "可按 OP / EB / ST 弹次浏览全卡表；首页与页脚补上对战、组牌等链接。",
      en: "Browse full set lists by OP / EB / ST, with crawlable links from home and the footer.",
    },
  },
  {
    id: "nav-more-binder-community-play-2026-09-20",
    date: "2026-09-20",
    kind: "fix",
    href: "/play",
    title: {
      "zh-Hant": "底欄「更多」改為卡冊、社區、對戰",
      "zh-Hans": "底栏「更多」改为卡册、社区、对战",
      en: "More menu now has Binder, Community, Play",
    },
    body: {
      "zh-Hant": "主列保留搜卡、組牌、賽事、收藏與價格；卡冊、社區、對戰收進「更多」。",
      "zh-Hans": "主列保留搜卡、组牌、赛事、收藏与价格；卡册、社区、对战收进「更多」。",
      en: "Search, decks, tournaments, collection, and prices stay on the bar; Binder, Community, and Play are under More.",
    },
  },
  {
    id: "nav-more-icon-size-2026-09-20",
    date: "2026-09-20",
    kind: "fix",
    href: "/prices",
    title: {
      "zh-Hant": "底欄「更多」選單圖示過大",
      "zh-Hans": "底栏「更多」菜单图标过大",
      en: "Bottom-nav More menu icons oversized",
    },
    body: {
      "zh-Hant": "點「更多」不再出現佔滿螢幕的巨大圖示，改回小圖示加文字。",
      "zh-Hans": "点「更多」不再出现占满屏幕的巨大图标，改回小图标加文字。",
      en: "Opening More no longer fills the screen with giant icons.",
    },
  },
  {
    id: "ux-p0-p1-2026-09-20",
    date: "2026-09-20",
    kind: "fix",
    href: "/play",
    title: {
      "zh-Hant": "對戰、搜尋與卡詳情更好用",
      "zh-Hans": "对战、搜索与卡详情更好用",
      en: "Faster play, search, and card pages",
    },
    body: {
      "zh-Hant": "可用範例卡組一鍵開戰；底欄不再擋住卡組+1；搜尋不再閃「共 0 張」；評論預設收起。",
      "zh-Hans": "可用范例卡组一键开战；底栏不再挡住卡组+1；搜索不再闪「共 0 张」；评论默认收起。",
      en: "One-tap sample AI battle, nav no longer covers +1, search skips the empty flash, and comments stay closed until you open them.",
    },
  },
  {
    id: "p-082-crocodile-base",
    date: "2026-09-20",
    kind: "fix",
    href: "/cards/P-082",
    title: {
      "zh-Hant": "P-082 克洛克達爾詳情頁可開",
      "zh-Hans": "P-082 克洛克达尔详情页可开",
      en: "P-082 Crocodile card page fixed",
    },
    body: {
      "zh-Hant": "底卡已入表；搜尋異畫再點進去不會再顯示找不到卡號。",
      "zh-Hans": "底卡已入表；搜索异画再点进去不会再显示找不到卡号。",
      en: "The base promo is now in the catalog, so opening P-082 from search no longer 404s.",
    },
  },
  {
    id: "op18-leaders-001-022-041-079",
    date: "2026-09-20",
    kind: "feature",
    href: "/cards/OP18-001",
    title: {
      "zh-Hant": "OP18 四張新領航加入卡表",
      "zh-Hans": "OP18 四张新领航加入卡表",
      en: "Four OP18 Leaders added",
    },
    body: {
      "zh-Hant": "飛毛腿、魯夫、Miss All星期天、斯帕達姆已可查卡並對戰。",
      "zh-Hans": "飞毛腿、路飞、Miss All星期天、斯帕达姆已可查卡并对战。",
      en: "Karoo, Monkey D. Luffy, Ms. All Sunday, and Spandam are now in the catalog and playable.",
    },
  },
  {
    id: "eb05-014-p1-shirahoshi-manga",
    date: "2026-09-20",
    kind: "feature",
    href: "/cards/EB05-014-P1",
    title: {
      "zh-Hant": "EB05-014 白星漫畫異畫加入卡表",
      "zh-Hans": "EB05-014 白星漫画异画加入卡表",
      en: "EB05-014 Shirahoshi manga art added",
    },
    body: {
      "zh-Hant": "漫畫風異畫已上架，效果與底卡相同：登場時找梅加羅或海王類，啟動可給海王類速攻。",
      "zh-Hans": "漫画风异画已上架，效果与底卡相同：登场时找梅加罗或海王类，启动可给海王类速攻。",
      en: "Manga parallel is live with the same effects as the base Shirahoshi.",
    },
  },
  {
    id: "eb05-sr-batch-2026-09-20",
    date: "2026-09-20",
    kind: "feature",
    href: "/cards/EB05-001",
    title: {
      "zh-Hant": "EB05 SR 一批加入卡表",
      "zh-Hans": "EB05 SR 一批加入卡表",
      en: "EB05 SR batch added",
    },
    body: {
      "zh-Hant": "珠寶・波妮、絲媞希小姐、白星、亞爾麗塔、砂糖、大和、嘉蘭、娜美已可查卡並對戰。",
      "zh-Hans": "珠宝・波妮、丝媞希小姐、白星、亚尔丽塔、砂糖、大和、嘉兰、娜美已可查卡并对战。",
      en: "Jewelry Bonney, Stussy, Shirahoshi, Alvida, Sugar, Yamato, Gloriosa, and Nami are now in the catalog and playable.",
    },
  },
  {
    id: "eb05-007-monet",
    date: "2026-09-20",
    kind: "feature",
    href: "/cards/EB05-007",
    title: {
      "zh-Hant": "EB05-007 莫奈加入卡表",
      "zh-Hans": "EB05-007 莫奈加入卡表",
      en: "EB05-007 Monet added",
    },
    body: {
      "zh-Hant": "登場時可公開合計3張事件或《龐克哈薩特》抽1；自己回合結束時此角色至對手結束階段前力量+5000。",
      "zh-Hans": "登场时可公开合计3张事件或《庞克哈萨特》抽1；自己回合结束时此角色至对手结束阶段前力量+5000。",
      en: "On Play you may reveal 3 Events or {Punk Hazard} to draw 1; End of Your Turn +5000 until opponent’s End Phase.",
    },
  },
  {
    id: "eb05-029-haori-ori",
    date: "2026-09-20",
    kind: "feature",
    href: "/cards/EB05-029",
    title: {
      "zh-Hant": "EB05-029 袴羽檻加入卡表",
      "zh-Hans": "EB05-029 袴羽槛加入卡表",
      en: "EB05-029 Haori Ori added",
    },
    body: {
      "zh-Hant": "主要：可棄1張手牌，使最多1張對手費用6以下角色本回合效果無效並回手；觸發抽2棄1。",
      "zh-Hans": "主要：可弃1张手牌，使最多1张对手费用6以下角色本回合效果无效并回手；触发抽2弃1。",
      en: "Main: you may trash 1 from hand to blank and bounce an opponent cost-6 or less Character; Trigger draw 2, trash 1.",
    },
  },
  {
    id: "st32-002-deny-rest-blocker-recheck",
    date: "2026-09-20",
    kind: "fix",
    href: "/play",
    title: {
      "zh-Hant": "再次確認光月御田「無法置為休息」會擋住阻擋",
      "zh-Hans": "再次确认光月御田「无法置为休息」会挡住阻挡",
      en: "Confirmed Oden rest-lock also blocks Blocker",
    },
    body: {
      "zh-Hant": "ST32-002 指定的角色（例如 OP16-045）在鎖定期間不能橫置發動【防禦】；僅被指定的那張生效，舊對局紀錄不會改寫。",
      "zh-Hans": "ST32-002 指定的角色（例如 OP16-045）在锁定期间不能横置发动【防御】；仅被指定的那张生效，旧对局记录不会改写。",
      en: "A Character locked by ST32-002 (e.g. OP16-045) cannot rest to Blocker; only the chosen copy is locked, and old replays are unchanged.",
    },
  },
  {
    id: "op16-032-deny-rest-attack-fix",
    date: "2026-09-20",
    kind: "fix",
    href: "/play",
    title: {
      "zh-Hant": "修正漢考克「無法置為休息」仍可進攻",
      "zh-Hans": "修正汉考克「无法置为休息」仍可进攻",
      en: "Fixed Hancock rest-lock still allowing attacks",
    },
    body: {
      "zh-Hant": "OP16-032 指定的角色到對手結束階段前無法休息；先前受害者回合仍可橫置宣言進攻，現已正確禁止。",
      "zh-Hans": "OP16-032 指定的角色到对手结束阶段前无法休息；先前受害者回合仍可横置宣言进攻，现已正确禁止。",
      en: "A Character locked by OP16-032 could still rest to attack on the victim's turn; attack declaration is now blocked while rest-lock lasts.",
    },
  },
  {
    id: "eb05-020-shirahoshi",
    date: "2026-09-20",
    kind: "feature",
    href: "/cards/EB05-020",
    title: {
      "zh-Hant": "EB05-020 我叫白星！！加入卡表",
      "zh-Hans": "EB05-020 我叫白星！！加入卡表",
      en: "EB05-020 I Am Shirahoshi!! added",
    },
    body: {
      "zh-Hant": "主要效果：可將自己的領航卡「白星」置為休息，抽2張。",
      "zh-Hans": "主要效果：可将自己的领航卡「白星」置为休息，抽2张。",
      en: "Main: you may rest your Leader Shirahoshi to draw 2 cards.",
    },
  },
  {
    id: "st32-002-deny-rest-blocker-fix",
    date: "2026-09-19",
    kind: "fix",
    href: "/cards/ST32-002",
    title: {
      "zh-Hant": "修正光月御田「無法置為休息」未擋下阻擋者",
      "zh-Hans": "修正光月御田「无法置为休息」未挡下阻挡者",
      en: "Fixed Kouzuki Oden's rest-lock not blocking Blocker",
    },
    body: {
      "zh-Hant": "ST32-002 指定的角色（例如 OP16-045）先前仍可發動【防禦】阻擋；現在「無法置為休息」期間會正確排除阻擋選項。",
      "zh-Hans": "ST32-002 指定的角色（例如 OP16-045）先前仍可发动【防御】阻挡；现在「无法置为休息」期间会正确排除阻挡选项。",
      en: "A character targeted by ST32-002 (e.g. OP16-045) could still activate Blocker; it's now correctly excluded from block options while the rest-lock is active.",
    },
  },
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
