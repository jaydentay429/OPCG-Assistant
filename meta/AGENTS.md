# meta

报告和评测产物。JSON 是大文件，只用 `rg` 查一条记录，禁止手改。

## 效果报告

`effect_audit_report.md`、`effect_fidelity_report.md`、`effect_fidelity_full_report.md`、`effect_problem_queue.md`、`effect_gap_tracker.md`、`effect_runtime_smoke.md`，以及同名 `.json`。由 `scripts/` 里的审计和编译脚本生成，步骤在 `scripts/README_EFFECTS.md`。

## 评测与名称

- `ai_eval_*.json`、`ai_eval_pool.json`、`ai_decks.json` 来自 `scripts/build_ai_eval_pool.py` 和 `scripts/ai_selfplay_eval.py`。
- `name_hans_by_en.json`、`name_aliases.json` 来自 `frontend/scripts/generate-hans-names.mjs`。要更新时重跑脚本，不要直接编辑。

日志 `sync_daily_pipeline.log` 和 `sync_daily_status.json` 由根目录 `sync_daily_pipeline.py` 追加。

## 其他生成物

- `limitless_meta.json`、`card_cooccurrence.json` 来自 `sync_limitless.py`，`app.py` 只读取。
- `card_attributes_map.json` 来自 `sync_card_attributes.py`。
- `residual_audit.json` 来自 `scripts/audit_residual_paper_encoding.py`。
- `price_check_result.json` 来自 `price_check_one.py --save`。
- `pack_image_md5.json` 记录本地卡图文件的 size、mtime、md5。不要手改；查单张用 `rg`。

这些 JSON 都是大文件。查一条用 `rg`，重新生成用对应脚本。

Markdown 报告可以读某一节，不要为了“了解全貌”把 `effect_fidelity_full_report.md` 整份读入。需要结论时先看 `scripts/README_EFFECTS.md` 里写的产物路径。

手改 JSON 会造成和索引不一致。发现内容过时时，重跑生成它的脚本。

`ai_eval_baseline.json` 是自评对照，不要为了让新跑分“变好”而改它。新结果另存，并在提交说明里写清对比的是哪一份。
