先读 `docs/INDEX.md`。不要整份读取标注为大文件的文件。

OPTCG 工具站：根目录 Python API（`app.py`）加 `frontend/` 的 Next.js 15，文案为繁中、简中、英文。

## 同步表

| 改动 | 同步更新 |
|---|---|
| 新增或删除 `frontend/src/app` 路由 | `frontend/AGENTS.md` 的路由列表，以及 INDEX 的目录地图 |
| 新增或删除文案 key | `en.ts`、`zh-Hans.ts`、`zh-Hant.ts` 一起改；`*.generated.ts` 用脚本重跑 |
| 新增 `sync_*.py` 或改数据流 | INDEX 的「数据流」，以及 `scripts/AGENTS.md` |
| 改对战规则或时机 | `battle/AGENTS.md` |
| 改部署方式 | INDEX 的「部署」，以及 `deploy/optcgassistant/README.txt` |
| 纯内部实现 | 不改文档 |

## 大文件

`index/*.json`、`meta/*.json`、`frontend/src/locales/*.generated.ts` 只用 `rg` 查，不要整份读。其余目录说明在 `docs/INDEX.md`。
