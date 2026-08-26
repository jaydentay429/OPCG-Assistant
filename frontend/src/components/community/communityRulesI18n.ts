import type { Lang } from "@/lib/i18n";

/** Pinned community rules thread id on production. Override if recreated. */
export const COMMUNITY_RULES_THREAD_ID = Number(
  process.env.NEXT_PUBLIC_COMMUNITY_RULES_THREAD_ID || "1",
);

type RulesCopy = { title: string; body: string; excerpt: string };

const ZH_HANS: RulesCopy = {
  title: "社区规则与免责声明（发帖前必读）",
  excerpt:
    "感谢你加入 OPCG 卡牌助手社区。在发帖前，请花一分钟阅读以下内容，这不仅是社区礼仪，也关系到每一位用户的账号安全与本站的正常运作。",
  body: `感谢你加入 OPCG 卡牌助手社区。在发帖前，请花一分钟阅读以下内容，这不仅是社区礼仪，也关系到每一位用户的账号安全与本站的正常运作。

---

## 一、关于本站性质

OPCG 卡牌助手是由玩家自发制作的**非官方粉丝工具与交流社区**，与 BANDAI（万代）、集英社（Shueisha）、东映动画（Toei Animation）及 ONE PIECE 原作者尾田荣一郎先生**不存在任何官方关联、授权或合作关系**。

本站及本社区的一切内容，均不代表官方立场，仅供玩家之间交流学习使用。

---

## 二、版权声明

ONE PIECE 卡牌游戏相关的卡牌设计、角色形象、图案、名称等知识产权，归属 Eiichiro Oda（尾田荣一郎）、集英社、东映动画、BANDAI Namco Entertainment 等权利方所有。

本社区仅为玩家提供讨论、组牌、规则交流的空间，不主张对上述版权内容拥有任何权利。用户在发帖中提及、引用相关内容，应限于合理的交流讨论范围。

---

## 三、发帖内容禁止事项

为维护社区健康运作、避免法律风险，以下内容**严禁发布**，一经发现将立即删除，情节严重者将封禁账号：

1. **禁止发布或交易未经官方授权的复刻卡、盗版卡、代工卡（俗称"仿卡""neng卡"等）相关信息**，包括但不限于购买渠道、代工联系方式、价格咨询等
2. **禁止发布侵犯他人版权的内容**，包括盗版卡图、扫描件、未授权转载的商业内容、破解资源链接等
3. **禁止发布虚假、欺诈、诱导消费的信息**
4. **禁止人身攻击、辱骂、骚扰、歧视性言论**
5. **禁止发布垃圾广告、无关链接、恶意刷屏内容**
6. **禁止利用匿名功能发布违反以上规则的内容**——匿名仅用于保护发帖者的身份展示，不代表内容审核豁免，后台仍保留必要的账号信息以便违规追溯处理

---

## 四、关于匿名发帖

本社区支持匿名发帖功能，方便用户更自由地交流。但请注意：

- 匿名仅隐藏你的**展示身份**，不代表你可以免责发布违规内容
- 系统后台会保留必要的账号与操作记录，如内容涉嫌违法或严重违规，本站将依据本规则进行处理，并在必要时配合相关权利方或有关部门的合理要求

---

## 五、举报与处理机制

如你发现任何违反以上规则的内容，欢迎使用帖子/评论旁的"举报"功能进行反馈。本站管理团队会及时审核处理。

对于经核实的侵权、违规内容，本站将：
- 第一时间删除相关内容
- 视情节对账号进行警告、禁言或封禁处理
- 如收到权利方的合理通知（如版权投诉），将依法配合处理，包括但不限于移除相关内容

---

## 六、免责条款

1. 本社区所有用户发布的内容（文字、图片、链接等，统称"用户生成内容"）均为**发帖者个人观点或行为**，不代表本站立场，本站不对用户生成内容的准确性、合法性、完整性承担责任
2. 因用户发布内容引发的任何纠纷、损失或法律责任，由发帖者本人承担，本站保留追究相关责任的权利
3. 本站保留在不另行通知的情况下，修改本规则、删除违规内容、限制或封禁违规账号的权利
4. 本规则如有更新，将以最新公布版本为准

---

## 七、写在最后

本站是一个由玩家做给玩家的非商业小工具与交流空间，希望大家珍惜这个来之不易的交流环境，共同维护一个友善、健康的讨论氛围。

如有任何疑问或建议，欢迎通过页面顶部邮箱联系管理员。

*本规则自发布之日起生效，最后更新日期：2026年8月*`,
};

const ZH_HANT: RulesCopy = {
  title: "社區規則與免責聲明（發帖前必讀）",
  excerpt:
    "感謝你加入 OPCG 卡牌助手社區。在發帖前，請花一分鐘閱讀以下內容，這不僅是社區禮儀，也關係到每一位用戶的帳號安全與本站的正常運作。",
  body: `感謝你加入 OPCG 卡牌助手社區。在發帖前，請花一分鐘閱讀以下內容，這不僅是社區禮儀，也關係到每一位用戶的帳號安全與本站的正常運作。

---

## 一、關於本站性質

OPCG 卡牌助手是由玩家自發製作的**非官方粉絲工具與交流社區**，與 BANDAI（萬代）、集英社（Shueisha）、東映動畫（Toei Animation）及 ONE PIECE 原作者尾田榮一郎先生**不存在任何官方關聯、授權或合作關係**。

本站及本社區的一切內容，均不代表官方立場，僅供玩家之間交流學習使用。

---

## 二、版權聲明

ONE PIECE 卡牌遊戲相關的卡牌設計、角色形象、圖案、名稱等知識產權，歸屬 Eiichiro Oda（尾田榮一郎）、集英社、東映動畫、BANDAI Namco Entertainment 等權利方所有。

本社區僅為玩家提供討論、組牌、規則交流的空間，不主張對上述版權內容擁有任何權利。用戶在發帖中提及、引用相關內容，應限於合理的交流討論範圍。

---

## 三、發帖內容禁止事項

為維護社區健康運作、避免法律風險，以下內容**嚴禁發布**，一經發現將立即刪除，情節嚴重者將封禁帳號：

1. **禁止發布或交易未經官方授權的複刻卡、盜版卡、代工卡（俗稱「仿卡」「neng卡」等）相關資訊**，包括但不限於購買渠道、代工聯絡方式、價格諮詢等
2. **禁止發布侵犯他人版權的內容**，包括盜版卡圖、掃描件、未授權轉載的商業內容、破解資源連結等
3. **禁止發布虛假、欺詐、誘導消費的資訊**
4. **禁止人身攻擊、辱罵、騷擾、歧視性言論**
5. **禁止發布垃圾廣告、無關連結、惡意刷屏內容**
6. **禁止利用匿名功能發布違反以上規則的內容**——匿名僅用於保護發帖者的身分展示，不代表內容審核豁免，後台仍保留必要的帳號資訊以便違規追溯處理

---

## 四、關於匿名發帖

本社區支援匿名發帖功能，方便用戶更自由地交流。但請注意：

- 匿名僅隱藏你的**展示身分**，不代表你可以免責發布違規內容
- 系統後台會保留必要的帳號與操作記錄，如內容涉嫌違法或嚴重違規，本站將依據本規則進行處理，並在必要時配合相關權利方或有關部門的合理要求

---

## 五、舉報與處理機制

如你發現任何違反以上規則的內容，歡迎使用帖子／評論旁的「舉報」功能進行反饋。本站管理團隊會及時審核處理。

對於經核實的侵權、違規內容，本站將：
- 第一時間刪除相關內容
- 視情節對帳號進行警告、禁言或封禁處理
- 如收到權利方的合理通知（如版權投訴），將依法配合處理，包括但不限於移除相關內容

---

## 六、免責條款

1. 本社區所有用戶發布的內容（文字、圖片、連結等，統稱「用戶生成內容」）均為**發帖者個人觀點或行為**，不代表本站立場，本站不對用戶生成內容的準確性、合法性、完整性承擔責任
2. 因用戶發布內容引發的任何糾紛、損失或法律責任，由發帖者本人承擔，本站保留追究相關責任的權利
3. 本站保留在不另行通知的情況下，修改本規則、刪除違規內容、限制或封禁違規帳號的權利
4. 本規則如有更新，將以最新公布版本為準

---

## 七、寫在最後

本站是一個由玩家做給玩家的非商業小工具與交流空間，希望大家珍惜這個來之不易的交流環境，共同維護一個友善、健康的討論氛圍。

如有任何疑問或建議，歡迎通過頁面頂部郵箱聯繫管理員。

*本規則自發布之日起生效，最後更新日期：2026年8月*`,
};

const EN: RulesCopy = {
  title: "Community Rules & Disclaimer (read before posting)",
  excerpt:
    "Thanks for joining the OPCG Card Assistant community. Please take a minute to read the following before you post — it covers community norms and helps keep accounts and the site safe.",
  body: `Thanks for joining the OPCG Card Assistant community. Please take a minute to read the following before you post — it covers community norms and helps keep every user's account and this site running safely.

---

## 1. About this site

OPCG Card Assistant is a **fan-made, unofficial tool and community** created by players. It has **no official affiliation, authorization, or partnership** with BANDAI, Shueisha, Toei Animation, or ONE PIECE creator Eiichiro Oda.

Nothing on this site or in this community represents an official position. Content is for player discussion and learning only.

---

## 2. Copyright

Intellectual property related to the ONE PIECE Card Game — including card designs, character likenesses, artwork, and names — belongs to Eiichiro Oda, Shueisha, Toei Animation, BANDAI Namco Entertainment, and other rights holders.

This community only provides a space for discussion, deckbuilding, and rules talk. We claim no rights over that copyrighted material. Mentions or quotes in posts should stay within fair discussion.

---

## 3. Prohibited posts

To keep the community healthy and reduce legal risk, the following is **strictly forbidden**. Violations will be removed; serious cases may lead to account bans:

1. **Do not post or trade information about unauthorized replicas, counterfeits, or proxy/"neng" cards**, including purchase channels, maker contacts, or price inquiries
2. **Do not post copyright-infringing material**, including pirated card scans, unauthorized commercial reprints, or cracked-resource links
3. **Do not post false, fraudulent, or scam-related information**
4. **No personal attacks, insults, harassment, or discriminatory speech**
5. **No spam ads, irrelevant links, or malicious flooding**
6. **Do not use anonymity to break these rules** — anonymity only hides your public display name; it is not a moderation exemption. We retain necessary account data for enforcement

---

## 4. Anonymous posting

Anonymous posting is supported for freer discussion. Please note:

- Anonymity only hides your **public identity**; it does not excuse rule-breaking
- We keep necessary account and action logs. If content is illegal or seriously abusive, we will act under these rules and may cooperate with rights holders or authorities when reasonably required

---

## 5. Reports & enforcement

If you see a violation, use the **Report** action next to the thread or comment. Our team will review it.

For confirmed infringement or rule breaks, we may:
- Remove the content promptly
- Warn, mute, or ban the account as appropriate
- Cooperate with lawful notices from rights holders (e.g. copyright complaints), including removing related content

---

## 6. Disclaimer

1. All user-posted content (text, images, links, etc. — "user-generated content") is the **poster's own views or actions**, not the site's. We are not responsible for its accuracy, legality, or completeness
2. Disputes, losses, or legal liability arising from user posts are the poster's responsibility; we reserve the right to pursue related claims
3. We may update these rules, remove violating content, or restrict/ban accounts without prior notice
4. If rules are updated, the latest published version applies

---

## 7. Closing

This is a non-commercial player-built tool and space. Please help keep discussion friendly and healthy.

Questions or suggestions: contact us via the email at the top of the page.

*These rules take effect from the publish date. Last updated: August 2026*`,
};

const BY_LANG: Record<Lang, RulesCopy> = {
  "zh-Hans": ZH_HANS,
  "zh-Hant": ZH_HANT,
  en: EN,
};

export function isCommunityRulesThread(th: { id: number }): boolean {
  return Number(th.id) === COMMUNITY_RULES_THREAD_ID;
}

export function communityRulesCopy(lang: Lang): RulesCopy {
  return BY_LANG[lang] || ZH_HANT;
}

export function localizeCommunityRulesThread<T extends { id: number; title: string; body?: string; excerpt?: string }>(
  th: T,
  lang: Lang,
): T {
  if (!isCommunityRulesThread(th)) return th;
  const copy = communityRulesCopy(lang);
  return {
    ...th,
    title: copy.title,
    ...(th.body !== undefined ? { body: copy.body } : {}),
    ...(th.excerpt !== undefined ? { excerpt: copy.excerpt } : {}),
  };
}
