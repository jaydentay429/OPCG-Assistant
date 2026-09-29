# scripts

这里是离线脚本。数据同步的 `sync_*.py` 和 `sync_daily_pipeline.py` 在仓库根目录，不在本目录。

## 分类

- 效果审计与编译：`audit_*`、`compile_*`、`fix_*`、`review_*`、`run_full_effect_scan.py`、`build_effect_problem_queue.py`。命令和产物路径见 `README_EFFECTS.md`，不要在这里重抄。
- 后台与运维：`admin_set_password.py`、`promote_forum_admin.py`、`configure_resend.py`、`send_daily_analytics_report.py`、`traffic_recount.py`。
- 卡图：`build_card_image_manifest.py`、`copy_new_pack_images_to_r2.py`。
- AI 评测：`build_ai_eval_pool.py`、`ai_selfplay_eval.py`、`ai_stuck_diagnose.py`，写出 `meta/ai_eval_*.json`。

新增根目录 `sync_*.py` 时，改 `docs/INDEX.md` 的数据流，并在上面补一行分类。

## 和别的目录的边界

- 根目录 `sync_official_cards.py`、`sync_card_images.py`、`sync_yuyutei_prices.py`、`sync_limitless.py`、`sync_card_attributes.py`、`sync_don_cards.py`、`sync_limited_variants.py`、`sync_preview_cards.py`、`sync_topdecks.py` 由 `sync_daily_pipeline.py` 按日调用。
- `patch_op17_*.py` 一类脚本改的是 `index/card_effect_overrides.json`。改完跑 `battle/tests` 里对应的测试，不要手改 `meta/*.json` 来“对上”结果。
- 效果命令的完整列表只放在 `README_EFFECTS.md`。本文件只保留分类，避免两处说明漂移。

## 跑之前

脚本默认在仓库根目录执行，例如 `python scripts/audit_card_effects.py`。它们会读 `index/cards_by_id.json`，但调用方不要把那份 JSON 读进对话。产物写到 `meta/`，规则见 `meta/AGENTS.md`。

`fix_batch_*.py` 和 `fix_semantic_*.py` 是按批次改效果覆盖的历史脚本。新的修复优先走 `README_EFFECTS.md` 里的循环，不要再复制出一批新的 `fix_batch_*`。

卡图相关还有 `build_card_image_manifest.py`（构建期校验清单）和 `copy_new_pack_images_to_r2.py`。它们不负责界面文案。

后台脚本会碰到账号和邮件配置。不要把密钥写进脚本或提交到仓库。

`send_daily_analytics_report.py` 读的是统计库，不是卡牌索引。排错时先看脚本顶部的路径常量。

`traffic_recount.py` 只读同一份统计库，按新的排除规则重算访客，不写库、不发信。线上没有把原始库放进仓库。在 VPS 上：

```bash
cd /opt/opcg/app && .venv/bin/python scripts/traffic_recount.py \
  --db /opt/opcg/app/meta/analytics.db \
  --auth-db /opt/opcg/app/meta/auth.db
```

也可以把 `--log` 指到合并访问日志或 Caddy JSON。那是按客户端 IP 计的另一口径，不是邮件日报的 visitor_id。

## 流量统计排除

日报统计会跳过下面几类访问，页面本身不变，搜索引擎仍可抓取。

QA、Playwright、Cursor 云端代理、Grok 盒子，以及自己写的脚本，请求要带上 `X-OPCG-Internal: 1`，或者 User-Agent 里带 `OPCG-Internal`。带上任意一个都不计入访客。Playwright 可以这样设：

```js
extraHTTPHeaders: { "X-OPCG-Internal": "1" }
```

HeadlessChrome、Playwright、puppeteer、python-requests、curl、wget、Go-http-client、node-fetch、axios、undici，以及 bot / crawler / spider / preview（含 Googlebot）也会被排除。数据中心 IP 用 `analytics/datacenter_cidrs.txt` 里的默认段，可用 `ANALYTICS_DATACENTER_CIDRS` 追加。

自己的电脑和手机不靠 IP。在服务器环境变量设置 `ANALYTICS_EXCLUDE_ME_TOKEN`（只放占位符进仓库）。浏览器打开 `/internal/exclude-me?token=<该值>` 一次，这台设备会写下长期 cookie；`revoke=1` 撤销。token 错误是 404。登录账号用 `ANALYTICS_EXCLUDE_USER_IDS` 和 `ANALYTICS_EXCLUDE_EMAILS`，不要把真实邮箱写进仓库。
