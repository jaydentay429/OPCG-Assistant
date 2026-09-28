# locales

界面文案是三份字典，卡名另有生成文件。不要整份读取 `*.generated.ts`。

## 三语

`en.ts`、`zh-Hans.ts`、`zh-Hant.ts` 的 key 必须一起增删。缺一个 key，另一种语言会落到空字符串。

## 生成文件

`nameHansByEn.generated.ts`、`hansPhraseFixes.generated.ts`、`nameAliases.generated.ts` 由 `frontend/scripts/generate-hans-names.mjs` 写出。在 `frontend/` 执行：

```bash
node scripts/generate-hans-names.mjs
```

禁止手改这三份文件，也禁止手改它同时写出的 `meta/name_hans_by_en.json`。

## 谁在用

- `src/lib/i18n.tsx` 保存 `Lang`（`zh-Hant`、`zh-Hans`、`en`），并按当前语言取字典。
- `src/lib/cardLocale.ts` 用 OpenCC 和上面的生成表，把卡名、别名显示成当前语言。

## 不要做

- 不要只改一种语言。三个字典的 key 集合应相同。
- 不要把卡名硬编码进 `en.ts` 来绕过生成表。卡名走 `cardLocale.ts`。
- 不要整份打开 `index/cards_by_id.json` 来对卡名。需要单卡时用 `rg`。
- 改完字典后看 `src/lib/i18n.tsx` 的 `DICTS` 是否仍指向这三份文件。不要在组件里另写一套文案表。
- 默认界面语言以 `i18n.tsx` 为准。本目录不决定路由。
