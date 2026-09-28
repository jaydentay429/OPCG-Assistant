# frontend

Next.js 15 App Router。页面在 `src/app`，客户端界面在 `src/components`，请求、卡组、文案和 SEO 在 `src/lib`。

## 路由

- `/` 首页
- `/search` 搜索，`/cards/[id]` 卡牌详情，`/sets` 与 `/sets/[code]` 系列
- `/builder` 构筑器，`/collector` 收藏，`/binder` 与 `/binder/s/[token]` 卡册
- `/prices` 价格，`/tournaments` 比赛卡组，`/photo` 拍照识卡
- `/community`、`/community/new`、`/community/[id]`、`/community/me`、`/community/admin`
- `/play` 对战（`[[...slug]]`）
- `/reset-password`，`/legal/terms`、`/legal/privacy`、`/legal/disclaimer`

## 职责

- `src/lib`：`api.ts` 调后端；`deck.tsx`、`deckShare.ts`、`deckStructure.ts` 管构筑；`i18n.tsx` 与 `cardLocale.ts` 管文案（见 `src/locales/AGENTS.md`）；`seo.ts` 管分享图和 JSON-LD。
- `src/components`：各页的 `*PageClient`，以及 `CardImg`、`CardWall`、`TopBar`、`BottomNav` 这类共用界面。

## 命令

在 `frontend/`：

```bash
npm run test:unit
npm run lint
npm run build
```

`npm run build` 会先检查卡图 manifest，再生成卡号列表。
