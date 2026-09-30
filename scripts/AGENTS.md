# scripts

这里是离线脚本。数据同步的 `sync_*.py` 和 `sync_daily_pipeline.py` 在仓库根目录，不在本目录。

## 分类

- 效果审计与编译：`audit_*`、`compile_*`、`fix_*`、`review_*`、`run_full_effect_scan.py`、`build_effect_problem_queue.py`。命令和产物路径见 `README_EFFECTS.md`，不要在这里重抄。
- 后台与运维：`admin_set_password.py`、`promote_forum_admin.py`、`configure_resend.py`、`send_daily_analytics_report.py`、`traffic_recount.py`。
- 卡图：`build_card_image_manifest.py`、`copy_new_pack_images_to_r2.py`、`fill_missing_pack_images_from_r2.py`、`generate_card_webp.py`。
- AI 评测：`build_ai_eval_pool.py`、`ai_selfplay_eval.py`、`ai_stuck_diagnose.py`，写出 `meta/ai_eval_*.json`。

新增根目录 `sync_*.py` 时，改 `docs/INDEX.md` 的数据流，并在上面补一行分类。

## 和别的目录的边界

- 根目录 `sync_official_cards.py`、`sync_card_images.py`、`sync_yuyutei_prices.py`、`sync_limitless.py`、`sync_card_attributes.py`、`sync_don_cards.py`、`sync_limited_variants.py`、`sync_preview_cards.py`、`sync_topdecks.py` 由 `sync_daily_pipeline.py` 按日调用。
- `patch_op17_*.py` 一类脚本改的是 `index/card_effect_overrides.json`。改完跑 `battle/tests` 里对应的测试，不要手改 `meta/*.json` 来“对上”结果。
- 效果命令的完整列表只放在 `README_EFFECTS.md`。本文件只保留分类，避免两处说明漂移。

## 跑之前

脚本默认在仓库根目录执行，例如 `python scripts/audit_card_effects.py`。它们会读 `index/cards_by_id.json`，但调用方不要把那份 JSON 读进对话。产物写到 `meta/`，规则见 `meta/AGENTS.md`。

`fix_batch_*.py` 和 `fix_semantic_*.py` 是按批次改效果覆盖的历史脚本。新的修复优先走 `README_EFFECTS.md` 里的循环，不要再复制出一批新的 `fix_batch_*`。

卡图相关还有 `build_card_image_manifest.py`（按 R2 对象体重建清单；`--merge-missing-from` 只补仓库里多出来的卡号，不改、不删已有条目）、`copy_new_pack_images_to_r2.py`（packs→R2 只补缺）、`fill_missing_pack_images_from_r2.py`（R2→packs 只补缺）和 `generate_card_webp.py`（由 PNG 另存 WebP，不覆盖原图）。它们不负责界面文案。

`generate_card_webp.py` 读取 R2 桶 `opcg-packs` 或本地 `packs/` 里的 `<ID>.png`，上传三份 WebP：宽 200、宽 320，以及与原图同像素的全尺寸。对象名带 PNG 内容哈希前 8 位，和 manifest 的 `?h=` 是同一个值；原图一变，键就变，旧对象留着。默认跳过已存在的 WebP，`--force` 才覆盖这些 WebP。脚本没有删除，也不会上传或覆盖 `.png`。每个新对象的 Cache-Control 是 `public, max-age=31536000, immutable`。

凭据只来自环境变量（仓库里不写值）：`R2_ACCESS_KEY_ID`、`R2_SECRET_ACCESS_KEY`，以及 `R2_ENDPOINT` 或 `R2_ACCOUNT_ID`（也认 `OPCG_R2_ENDPOINT`、`OPCG_R2_ACCOUNT_ID`、`CLOUDFLARE_ACCOUNT_ID`）。桶名默认 `opcg-packs`，可用 `R2_BUCKET` 或 `OPCG_R2_BUCKET`。进程会读仓库根的 `.env`，但已经导出的环境变量优先。

在仓库根目录，先看 20 张会新增哪些键，再正式跑（中断后重跑会跳过已有 WebP）：

```bash
python3 scripts/generate_card_webp.py --from-r2 --dry-run --limit 20
python3 scripts/generate_card_webp.py --from-r2
```

每日官方同步在补完 PNG 之后用 `--packs` 再跑一次，只补还没有的 WebP。失败只记日志，后面的 manifest 照常重建。

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

统计库不保存原始 IP，也不保存邮箱。写入时用当时的 CIDR 名单判断，只存 `ip_is_datacenter`（0 或 1）。之后改 CIDR 名单或 `ANALYTICS_DATACENTER_CIDRS` 只影响新写入的浏览，不会回头重算已有行。邮箱在写入时用当前登录用户的地址做判断，库里只留下是否排除；重算时只用 `user_id` 去 `auth.db` 只读反查。User-Agent 截断到 300 字后保存，供 bot 规则重算。`--log` 只在当次进程里用日志中的 IP 算出同一个标志，不写回统计库。

自己的电脑和手机不靠 IP。在服务器环境变量设置 `ANALYTICS_EXCLUDE_ME_TOKEN`（只放占位符进仓库）。浏览器打开 `/internal/exclude-me?token=<该值>` 一次，这台设备会写下长期 cookie；`revoke=1` 撤销。token 错误是 404。登录账号用 `ANALYTICS_EXCLUDE_USER_IDS` 和 `ANALYTICS_EXCLUDE_EMAILS`，不要把真实邮箱写进仓库。
