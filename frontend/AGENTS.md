# frontend

Next.js 15 App Router。页面在 `src/app`，客户端界面在 `src/components`，请求、卡组、文案和 SEO 在 `src/lib`。

## 路由

- `/` 首页
- `/search` 搜索，`/cards/[id]` 卡牌详情，`/sets` 与 `/sets/[code]` 系列
- `/builder` 构筑器，`/collector` 收藏，`/binder` 与 `/binder/s/[token]` 卡册
- `/prices` 价格，`/tournaments` 比赛卡组，`/photo` 拍照识卡
- `/leaders` 领袖列表，`/leaders/[id]` 领袖统计（出场、冠军卡组、常用卡）。数据来自 API `/topdecks/leaders`；少于 5 副卡组的领袖页 `noindex`，不进 sitemap
- 语言网址：`/`、`/search`、`/builder`、`/tournaments`、`/prices`、`/sets*`、`/cards/*`、`/leaders*` 另有 `/en/...` 和 `/zh-hans/...`。不带前缀的是繁中（网址不变）。`src/middleware.ts` 把前缀改写成原路由并带请求头 `x-opcg-lang`，根 layout 用它定 `<html lang>`、canonical 和 hreflang（`src/lib/localeRouting.ts`）。其它路由带前缀会 308 到无前缀地址；`/zh-hant/*` 301 到无前缀地址。因为读请求头，这些页面是动态渲染。`next.config.ts` 的 `skipMiddlewareUrlNormalize` 不要删：VPS 上 `HOSTNAME=127.0.0.1`，去掉后改写会被当成外部代理，语言请求头丢失，`/en` 会显示繁中
- `/alerts/unsubscribe` 邮件提醒一键退订（noindex）
- `/community`、`/community/new`、`/community/[id]`、`/community/me`、`/community/admin`
- `/play` 对战大厅（房间、匹配、AI）；`/play/rank` 排位；`/play/history` 与 `/play/history/[id]` 记录和回放；`/play/spectate` 观战。这些页面 `noindex,follow`，不进 sitemap
- `/reset-password`，`/legal/terms`、`/legal/privacy`、`/legal/disclaimer`
- `/internal/exclude-me` 不公开、不索引。token 不对返回 404。不要把带 token 的地址写进公开说明

## 职责

- `src/lib`：`api.ts` 调后端；`deck.tsx`、`deckShare.ts`、`deckStructure.ts` 管构筑；`i18n.tsx` 与 `cardLocale.ts` 管文案（见 `src/locales/AGENTS.md`）；`seo.ts` 管分享图和 JSON-LD；`localeRouting.ts`、`serverCopy.ts` 管语言网址和服务端文案（简中由 OpenCC 从繁中转）。
- `src/components`：各页的 `*PageClient`，以及 `CardImg`、`CardWall`、`TopBar`、`BottomNav` 这类共用界面。

## 命令

在 `frontend/`：

```bash
npm run test:unit
npm run lint
npm run build
```

`npm run build` 会先检查卡图 manifest，再生成卡号列表。
