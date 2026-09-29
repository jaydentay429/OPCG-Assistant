# battle

对战引擎。改规则或时机时同步本文件。不要整份读取 `index/cards_by_id.json`。

## 分层

- 对局：`engine.py` 处理动作与合法性，`state.py` 保存局面。`rooms.py`、`routes.py`、`matchmaking.py` 管房间和接口。另有 `replay.py`、`spectator.py`、`rank.py`。
- 效果：`effects.py`、`effect_library.py`、`effect_schema.py`、`effect_fidelity.py`、`effect_audit.py`。
- AI：`ai.py`、`ai_decks.py`。
- 规则：`rules/catalog.py` 记录规则条目和实现状态，`rules/checkpoints.py` 是规则处理点，`rules/timings.py` 把关键词时机映射到引擎 timing。

## 效果数据

人工覆盖写在 `index/card_effect_overrides.json`，由 `effect_library.py` 读取。用 `rg` 查单卡，不要整份打开。

## 测试

在仓库根目录：

```bash
python -m pytest battle/tests
python -m pytest battle/tests/test_rules_checkpoints.py
```

改某张卡的效果后，跑对应的 `battle/tests/test_<id>.py`。改时机或规则处理点时，再跑 `test_rules_checkpoints.py`。根目录 `tests/` 测的是 API 和同步，不能代替这里的对局测试。

`rules/timings.py` 里的 timing 字符串要和 `effect_schema.py` 保持一致。改一边时核对另一边，并更新本文件的分层说明。

不要在本目录改前端或 API 路由以外的展示文案。对战页面在 `frontend/src/app/play`。本文件只描述引擎分层和测试，不记录单卡效果。

单卡覆盖用 `rg` 查 `index/card_effect_overrides.json`。AI 选着的测试在 `battle/tests/test_ai_heuristic.py`。
