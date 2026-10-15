# battle

对战引擎。改规则或时机时同步本文件。不要整份读取 `index/cards_by_id.json`。

## 分层

- 对局：`engine.py` 处理动作与合法性，`state.py` 保存局面。`rooms.py`、`routes.py`、`matchmaking.py` 管房间和接口。另有 `replay.py`、`spectator.py`、`rank.py`。
- 卡组合法：`official_restriction.py` 读取 `index/official_restriction_list.json`。玩家提交的卡组若含已生效的官方禁用卡、超过张数的限制卡或禁用组合，房间、匹配、排位和卡组写入都会拒绝。系列开放日在 `index/set_legality.json`（前后端共用，按马来西亚日期）：休闲、房间和 AI 从发售日起，且该卡要有可执行的对战效果数据；排位从比赛合法日起，同样要有效果数据。没有效果数据的卡继续挡下。OP18 的比赛合法日按发售后 7 日暂定。指定的 AI 卡组在开房时走同一条休闲检查。环境变量 `OPCG_BATTLE_TODAY=YYYY-MM-DD` 在值合法时当作当天，未设置或格式不对则仍用马来西亚当天；`GET /battle/ai-decks` 的 `battle_date` 给对战页做导入检查，不看浏览器时钟。
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
