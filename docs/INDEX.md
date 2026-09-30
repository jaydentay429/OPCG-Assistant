# OPCG Assistant

OPTCG 工具站：Python API 加 Next.js 前端，界面为繁中、简中、英文。

先看本页。标注为大文件的 JSON 和生成文件只用 `rg` 查，不要整份读。

## 目录地图

| 路径 | 内容 |
|---|---|
| `app.py` | FastAPI：卡牌、卡组、价格、图片 |
| `sync_*.py`、`sync_daily_pipeline.py` | 每日数据同步（在仓库根目录） |
| `battle/` | 对战引擎，见 `battle/AGENTS.md` |
| `frontend/` | Next.js 15，见 `frontend/AGENTS.md`。另有不索引的 `/internal/exclude-me` |
| `frontend/src/locales/` | 三语文案，见该目录 `AGENTS.md` |
| `scripts/` | 效果审计、后台、卡图脚本，见 `scripts/AGENTS.md` |
| `meta/` | 报告和评测产物，见 `meta/AGENTS.md` |
| `index/` | 卡牌索引 JSON |
| `tests/` | API 与同步的 Python 测试 |
| `forum/`、`analytics/` | 社区与访问统计 |
| `deploy/` | Caddy、systemd、每日同步壳脚本 |
| `preview/`、`static/` | 预览页和静态资源 |
| `.github/workflows/deploy.yml` | 推到 `main` 后部署到 VPS |

## 数据流

官方或第三方来源 → 根目录 `sync_official_cards.py`、`sync_yuyutei_prices.py`、`sync_limitless.py` 等，由 `sync_daily_pipeline.py` 串起来 → `index/*.json` → `app.py` → `frontend/`。

卡图 WebP 由 `scripts/generate_card_webp.py` 从 PNG 另存到 R2（不覆盖原 PNG）。列表页用 manifest 里同一个 `?h=` 拼缩略图地址；WebP 还没有时回退到 PNG。

效果文本另外走 `scripts/compile_card_effects.py` 与审计脚本，人工修正落在 `index/card_effect_overrides.json`，对战引擎从这里读。界面简中卡名由 `frontend/scripts/generate-hans-names.mjs` 写入 locale 生成文件和 `meta/name_hans_by_en.json`。

## 关键文件

- `app.py`：HTTP API
- `sync_daily_pipeline.py`：每日同步入口
- `battle/ai.py`：对战 AI 选着
- `frontend/src/lib/i18n.tsx`：界面语言

## 文档地图

- `scripts/README_EFFECTS.md`：效果编译、审计、修复循环
- `frontend/README.md`：本地 API 与前端开发
- `deploy/optcgassistant/README.txt`：VPS、Caddy、systemd
- `meta/effect_*.md`：效果审计报告（生成物，见 `meta/AGENTS.md`）

## 部署

`.github/workflows/deploy.yml` 在 `main` 上构建前端并同步到 VPS。连接用 GitHub Actions secrets `VPS_SSH_KEY`、`VPS_HOST`、`VPS_USER`（只写名字，值在仓库 Secrets 里）。站点与 API 的反代、服务文件在 `deploy/optcgassistant/`。每日官方同步先把 packs 里 R2 还没有的 `<ID>.png` 补上 R2，再从 R2 只补本地缺失的卡图（不覆盖已有文件），然后为还没有的 WebP 衍生图补 w200、w320 和全尺寸（失败只记日志），最后按 R2 对象体重建 manifest。衍生图文件名带内容哈希，manifest 解析会跳过它们，清单仍然只记 PNG 的哈希。

## 大文件

不要整份读取：

- `index/*.json`（含 `cards_by_id.json`、`card_effect_overrides.json`）
- `meta/*.json`（效果报告、`ai_eval_*.json`）
- `frontend/src/locales/*.generated.ts`

目录职责的同步表在根 `AGENTS.md`。

结构安排参考了 Elisa 的分层说明方式，正文是按本仓库写的。
