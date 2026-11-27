# optcgassistant.com（海贼王卡牌 OPCG 资讯/工具站）

通用规矩见 ~/.claude/CLAUDE.md。本文件只写这个项目的事。

## 目的
- 玩家工具站：卡表搜索、卡价（日本 Yuyutei）、卡组、赛事 meta、领袖统计、新卡预览。
- 语言：繁中（默认）、简中（`/zh-hans`）、英文（`/en`），不再加别的语言。用户主要在华语地区和英语国家。
- **不要和 itchyme（YouTube 频道）互链、互推。**（怕网站版权风险连累频道。）

## 技术栈
- 后端：根目录 Python FastAPI（`app.py`）+ 每日同步脚本（`sync_*.py`，由 `sync_daily_pipeline.py` 串起来）；卡牌资料存成 `index/*.json`；`battle/` 是对战引擎。
- 前端：`frontend/` 下 Next.js 15 App Router + React 19，opencc 做繁简转换。
- 卡图在 Cloudflare R2，经 `img.optcgassistant.com`；API 在 `api.optcgassistant.com`。
- 服务器：DigitalOcean 新加坡 1GB Droplet，Caddy + systemd（服务 `opcg-api`、`opcg-web`）。

## 仓库和部署
- 仓库 `jaydentay429/OPCG-Assistant`（**公开**），分支 `main`。公开仓库，更要注意不提交任何 secret。
- 推到 `main` 后，GitHub Actions `deploy.yml` 构建前端，rsync 到 VPS 并重启服务。
- **没有 PR CI**，本地测试结果就算数：前端 `npm run test:unit`、`npm run build`；后端 `pytest`。
- 每日定时：02:00 MYT 同步新卡图到 R2（只补缺的，不覆盖人工换过的图）；价格同步约 12:00 和 16:00 MYT。

## 合并规矩
- 合并窗口：12:30–13:00 和 17:00–18:00 MYT（避开价格同步）；合并前要先通知 QA。
- Jayden 明确说可以时，窗口外也能合并。他自己有时也会直接合并，看到意外的合并多半是他。
- 简单改动（文案、小修、新增文案 key）测试和 build 通过可以直接合并，但要在合并窗口内；价格同步、服务器部署、爬虫相关的改动仍要他说「合并」。

## 代码规矩
- 先读 `AGENTS.md` 和 `docs/INDEX.md`。`index/*.json`、`meta/*.json`、`*.generated.ts` 很大，只用 `rg` 查。
- 新增文案 key 时三种语言的文件一起改。
- `index/card_effects.json` 在服务器上生成，仓库里只留 0 字节占位文件，不要提交内容。
- 卡图：官方还没出图可以先用其他来源；官方出了就换成官方图，**优先日文版**。人工换过的图（Robin、大和、山梶）不要被同步覆盖。
- 对战功能 `/play`：因 Bandai 版权风险曾下线，2026-10-13 他说要重开；现在 noindex、不进 sitemap。
- 卡牌效果、规则一定要准确，不确定就标出来，不要编。

## 现况（PR #81 已上线）
- 领袖页：131 个领袖有 5 套以上卡组；sitemap 已收 396 个领袖网址。
- 赛事页卡图改成 WebP，CLS 0.255 → 0.057。新卡/价格提醒邮件功能已做，开关关着。
- sitemap 共 11,770 个网址（不含新增领袖页）。

## 待确认 / 已知问题
- 卡价：5,481 张卡里 906 张没价格，3,604 张超过 60 天没更新。代码已改成优先更新最久没查的卡，但服务器定时任务和日志还没查：要 Jayden 登录服务器，把 `/opt/opcg/logs/daily_price_latest.log` 和 crontab 内容发来。
- 有 3 个价格同步测试本来就失败（main 上也一样），不是 #81 造成的。
- 广告：暂时不做。
- 例行检查（新环境要重新设置）：每天约 10:00 MYT（含周末）看官方 X @ONEPIECE_tcg 和 @ONEPIECE_tcg_EN，有新卡、新卡包、卡表或规则时才通知他，说明网站有没有、问他要不要加。

## SEO
- 每张卡一页，sitemap 用每张卡真实的更新日期。
- 领袖统计页只有 5 套以上卡组才收录。赛事标题用最新 meta，不写死系列号。
- 同时考虑 AEO / GEO。
